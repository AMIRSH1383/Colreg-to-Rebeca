"""Run the COLREG pipeline, pausing only for the host's existing LLM agents."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import sys
from uuid import uuid4
import xml.etree.ElementTree as ET

from jsonschema import ValidationError, validate

from scripts.binding import semantic_binding as binding
from scripts.extraction import rebeca_extractor
from scripts.synthesis import synthesis
from scripts.utilities.experiment_store import (
    REQUIRED, ROOT, STAGES, Experiment, atomic_json, digest, path_key, snapshot,
)
from scripts.utilities.stage_cli import managed_main
from verification import verify_gate

LLM = {
    'colreg_extraction': ('colreg_extractor', 'colreg-extractor.schema.json'),
    'binding': ('semantic_binding_agent', 'semantic-binding.schema.json'),
    'synthesis': ('synthesis_agent', 'synthesis.schema.json'),
}
RULES = {
    'rule3b': ('Rule3b', 'Rule-3b', 'Rule3b.txt'),
    'rule6ai': ('Rule6ai', 'Rule-6ai', 'Rule6ai.txt'),
    'rule13b': ('Rule13b', 'Rule-13b', 'Rule13b.txt'),
    'rule23a': ('Rule23a', 'Rule-23a', 'Rule23a.txt'),
    'rule22a': ('Rule22a', 'Rule-22a', 'Rule22_baseline_colreg.txt'),
    'rule19ab': ('Rule19ab', 'Rule-19', 'Rule19_baseline_colreg.txt'),
    'rule19': ('Rule19ab', 'Rule-19', 'Rule19_baseline_colreg.txt'),
}
RMC_CONFIG = ROOT / 'verification/rmc/configs/rmc_timing_fixed.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def schema(name):
    return read(ROOT / 'schemas' / name)


def rule_inputs(rule, colreg, model):
    folder, agent_id, filename = RULES.get(rule.replace('-', '').casefold(), (rule, rule, None))
    if colreg is None:
        if filename is None:
            raise ValueError(f'No default COLREG source for {rule}. Supply --colreg.')
        colreg = ROOT / 'inputs/colreg' / filename
    model = model or ROOT / 'inputs/rebeca/original_model.rebeca'
    for path in (colreg, model):
        if not path.is_file():
            raise ValueError(f'Missing pipeline input: {path}')
    return folder, agent_id, colreg.resolve(), model.resolve()


def verification_summary(result, xml):
    status = result['verification_status']
    xml_status = None
    if xml and xml.is_file():
        try:
            xml_status = ET.parse(xml).findtext('checked-property/result')
        except (OSError, ET.ParseError):
            pass
    if xml_status:
        model_errors = {'queue overflow': 'queue_overflow', 'deadlock': 'deadlock',
                        'deadline missed': 'deadline_missed'}
        status = model_errors.get(xml_status.strip().casefold(), status)
    details = result['rmc_details']
    result_artifact = details.get('result_artifact', {})
    execution = details.get('model_out', {})
    error = execution.get('error') or result_artifact.get('error')
    if not error and status in {'verification_failed', 'compilation_failed', 'execution_failed'}:
        error = details.get('rmc_outcome') or status
    return {
        'outcome': status, 'gate_status': result['verification_status'],
        'rmc_result': xml_status, 'rmc_outcome': details.get('rmc_outcome'),
        'optional_checks': result['optional_checks'], 'error': error,
        'checker_exit_code': execution.get('exit_code'),
    }


class Coordinator:
    def __init__(self, args):
        rule, self.agent_id, self.colreg, self.model = rule_inputs(args.rule_id, args.colreg, args.model)
        self.exp = Experiment(rule, args.experiments_dir)
        self.jar = (args.jar or ROOT / read(RMC_CONFIG)['jar']).resolve()
        self.mode = 'full_rerun' if args.full_rerun else 'reuse'
        self.work = self.exp.work_root / 'coordinator'
        self.state_path = self.work / 'state.json'
        self.report_path = self.exp.folder / 'coordinator_report.json'
        self.state = {}

    def stage_inputs(self, stage):
        folder = self.exp.folder
        colreg = folder / 'colreg_extraction.json'
        rebeca = folder / 'rebeca_extraction.json'
        bound = folder / 'semantic_binding.json'
        return {
            'colreg_extraction': (self.colreg,),
            'rebeca_extraction': (self.model,),
            'binding': (colreg, rebeca),
            'synthesis': (colreg, bound, rebeca, self.model),
            'verification': (folder / 'synthesis/model.rebeca', folder / 'synthesis/model.property', self.jar),
        }[stage]

    def contracts(self, stage):
        if stage in LLM:
            agent, contract = LLM[stage]
            return (ROOT / 'agents' / f'{agent}.md', ROOT / 'schemas' / contract)
        return ()

    def stages_current(self):
        records = self.exp.inspect()['stages']
        for stage, completed in self.state['stages'].items():
            if completed['status'] not in {'executed', 'reused'}:
                continue
            record = records[stage]
            if record['status'] != 'current' or record['last_success'] != completed['last_success']:
                raise ValueError(f'{stage} changed since this Coordinator invocation began')

    def validate_colreg(self, value):
        validate(value, schema('colreg-extractor.schema.json'))
        if value['status'] != 'ok':
            raise ValueError(value['message'])
        if value['rule_id'] != self.agent_id:
            raise ValueError(f'Expected extraction rule_id {self.agent_id}, got {value["rule_id"]}')
        source = self.colreg.read_text(encoding='utf-8-sig')
        extraction = value['extraction']
        if any(item['source_text'] not in source for key in ('entities', 'statements')
               for item in extraction[key]):
            raise ValueError('Extraction source quotation is absent from the selected COLREG input')

    def validate_verification(self, payload):
        validate(payload, schema('verification.schema.json'))

    def check_reuse(self, stage):
        if self.mode != 'reuse':
            return False
        current = self.exp.inspect()['stages'][stage]
        if current['status'] != 'current':
            return False
        success = current['last_success']
        if not REQUIRED[stage] <= success['artifacts'].keys():
            return False
        return all(sha is not None and success['inputs'].get(key) == sha
                   for key, sha in snapshot(self.stage_inputs(stage)).items())

    def managed(self, stage, runner, args, *, expected=None):
        common = ['--rule', self.exp.rule, '--experiments-dir', str(self.exp.folder.parent)]
        if expected is None:
            expected = snapshot(self.stage_inputs(stage))
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = managed_main(
                stage, common + args, runner, expected_inputs=expected,
                contract_inputs=self.contracts(stage),
                validate_outputs=lambda work: self.validate_output(stage, work, scratch=True),
            )
        if code not in (None, 0):
            raise ValueError(stderr.getvalue().strip() or f'{stage} runner exited with code {code}')
        return json.loads(stdout.getvalue())

    def request(self, stage):
        agent, contract = LLM[stage]
        paths = self.stage_inputs(stage)
        tracked = snapshot((*paths, *self.contracts(stage)))
        if None in tracked.values():
            raise ValueError(f'Missing inputs for {stage}')
        response = self.work / 'agent-response.json'
        response.unlink(missing_ok=True)
        if stage == 'colreg_extraction':
            data = {'rule_id': self.agent_id, 'colreg_input': str(self.colreg), 'output_file': str(response)}
        elif stage == 'binding':
            colreg, rebeca = map(read, paths)
            binding.validate_inputs(colreg, rebeca)
            data = {'colreg_extraction': colreg, 'rebeca_extraction': binding.compact_inventory(rebeca)}
        else:
            prepared = self.managed('synthesis', synthesis._main,
                                    ['--model', str(self.model), '--prepare-only'], expected=tracked)
            data = read(prepared['request'])
        request = {
            'request_id': uuid4().hex, 'stage': stage, 'agent': agent,
            'instructions': str(self.contracts(stage)[0]), 'schema': str(ROOT / 'schemas' / contract),
            'input': data, 'response_path': str(response),
        }
        self.state['pending'] = {'request_id': request['request_id'], 'stage': stage, 'inputs': tracked}
        atomic_json(self.work / 'request.json', request)
        atomic_json(self.state_path, self.state)
        return {
            'status': 'awaiting_agent', 'rule': self.exp.rule, 'stage': stage,
            'agent': agent, 'request_id': request['request_id'], 'request': str(self.work / 'request.json'),
            'response_path': str(response),
        }

    def import_response(self, stage, response, expected):
        if stage == 'colreg_extraction':
            with self.exp.attempt(stage, [*self.stage_inputs(stage), *self.contracts(stage), response],
                                  provenance={'execution': 'coordinator_agent_response'}) as attempt:
                if any(attempt.inputs.get(key) != value for key, value in expected.items()):
                    raise ValueError('Extraction inputs changed after the LLM request')
                self.validate_colreg(read(response))
                attempt.publish({'colreg_extraction.json': response}, transient_inputs=[response])
        elif stage == 'binding':
            self.managed(stage, binding._main, ['--response', str(response)], expected=expected)
        else:
            self.managed(stage, synthesis._main,
                         ['--model', str(self.model), '--response', str(response)], expected=expected)

    def record(self, stage, status):
        record = self.exp.inspect()['stages'][stage]
        for name in REQUIRED[stage]:
            if not (self.exp.folder / name).is_file():
                raise ValueError(f'Missing stage output: {name}')
        if record['status'] != 'current':
            raise ValueError(f'{stage} output is stale')
        self.state['stages'][stage] = {'status': status, 'last_success': record['last_success']}

    def validate_output(self, stage, folder, *, scratch=False):
        """Check published cache entries and validate runner outputs before promotion."""
        if stage == 'colreg_extraction':
            return self.validate_colreg(read(folder / 'colreg_extraction.json'))
        if stage == 'rebeca_extraction':
            return validate(read(folder / 'rebeca_extraction.json'), schema('rebeca_extraction.schema.json'))
        if stage == 'binding':
            # The binding runner already validates responses before writing.
            if not scratch:
                colreg, rebeca = map(read, self.stage_inputs(stage))
                binding.validate_result(read(folder / 'semantic_binding.json'), colreg, rebeca,
                                        schema('semantic-binding.schema.json'))
        elif stage == 'synthesis':
            output = folder / ('result' if scratch else 'synthesis')
            response = read(output / 'response.json')
            if not scratch:
                colreg, bound = map(read, self.stage_inputs(stage)[:2])
                request, model = synthesis.prepare(colreg, bound, self.model.read_bytes())
                synthesis.validate_response(response, request, model)
            report = read(output / 'report.json')
            if digest(output / 'model.rebeca') != report['model_sha256']:
                raise ValueError('Synthesis model does not match its report')
            prop = output / 'model.property'
            if prop.is_file() != report['property_generated']:
                raise ValueError('Synthesis Property availability disagrees with its report')
            if prop.is_file() and prop.read_text() != response['property_content']:
                raise ValueError('Synthesis Property disagrees with the validated response')
        elif stage == 'verification':
            self.validate_verification(read(folder / ('result' if scratch else 'verification') / 'result.json'))

    def report(self, status, error=None):
        folder = self.exp.folder
        stages = dict(self.state['stages'])
        verification = self.state.get('verification')
        current = self.exp.inspect()['stages']
        processed = {
            stage for stage, record in stages.items()
            if record['status'] in {'executed', 'reused'} and current[stage]['status'] == 'current'
            and current[stage]['last_success'] == record['last_success']
        }
        for stage, record in stages.copy().items():
            if record['status'] in {'executed', 'reused'} and stage not in processed:
                stages[stage] = {'status': 'stale'}
            elif stage in processed:
                stages[stage] = {'status': record['status'],
                                 'artifacts': sorted(record['last_success']['artifacts'])}
        if 'verification' not in processed and stages.get('verification', {}).get('status') != 'failed':
            verification = None
        bound = read(folder / 'semantic_binding.json') if 'binding' in processed else {}
        synthesis_report = read(folder / 'synthesis/report.json') if 'synthesis' in processed else {}
        colreg = read(folder / 'colreg_extraction.json') if 'colreg_extraction' in processed else {}
        llm = self.state['llm']
        totals = {}
        for key in ('input_tokens', 'output_tokens'):
            totals[key] = sum(call[key] for call in llm) if all(call[key] is not None for call in llm) else None
        report = {
            'rule': self.exp.rule, 'rule_id': self.agent_id, 'status': status, 'mode': self.mode,
            'stages': {**{stage: stages.get(stage, {'status': 'not_run'}) for stage in STAGES},
                       'reporting': {'status': 'executed'}},
            'model': path_key(folder / 'synthesis/model.rebeca') if synthesis_report else None,
            'property': path_key(folder / 'synthesis/model.property') if synthesis_report.get('property_generated') else None,
            'verification': verification,
            'freshness_manifest': path_key(self.exp.manifest),
            'incomplete_checks': [
                name for name, value in (verification or {}).get('optional_checks', {}).items()
                if value in {'disabled', 'not_run', 'unknown'}
            ],
            'binding_status': bound.get('status'),
            'synthesis_status': synthesis_report.get('status'),
            'binding_unresolved': bound.get('unresolved_concepts', []),
            'unresolved': synthesis_report.get('unresolved', []),
            'semantic_uncertainties': synthesis_report.get('semantic_uncertainties', {}),
            'open_assumptions': synthesis_report.get('open_assumptions', colreg.get('open_assumptions', [])),
            'interpretation': synthesis_report.get('interpretation'),
            'regulatory_compliance': 'not_established',
            'llm': {'passes_reported_this_invocation': len(llm), **totals, 'passes': llm},
            'error': error,
        }
        target = self.work / 'last-report.json'
        atomic_json(target, report)
        if status in {'completed', 'partial'}:
            atomic_json(self.report_path, report)
            target = self.report_path
        return {'status': status, 'rule': self.exp.rule, 'report': str(target), 'error': error}

    def advance(self, args):
        if args.resume:
            self.state = read(self.state_path)
            pending = self.state.get('pending')
            if not pending or args.resume != pending['request_id'] or self.state['selection'] != self.selection():
                raise ValueError('No matching pending request for this rule, inputs, and run mode')
            self.state['llm'].append({
                'stage': pending['stage'], 'execution': args.execution, 'input_tokens': args.input_tokens,
                'output_tokens': args.output_tokens, 'status': 'failed' if args.agent_error else 'response_received',
            })
        else:
            self.state = {'selection': self.selection(), 'stages': {}, 'llm': [], 'pending': None}

        for stage in STAGES:
            if stage in self.state['stages']:
                continue
            prior_verification_attempt = (self.exp.inspect()['stages'][stage].get('last_attempt')
                                          if stage == 'verification' else None)
            try:
                self.stages_current()
                if stage == 'verification' and not (self.exp.folder / 'synthesis/model.property').is_file():
                    self.state['stages'][stage] = {'status': 'skipped', 'reason': 'Synthesis produced no supported Property'}
                    return self.report('partial')
                if stage == 'verification' and digest(self.jar) != read(RMC_CONFIG)['sha256']:
                    raise ValueError(f'Missing or incorrect timing-corrected RMC JAR at {self.jar}. '
                                     'Build the pinned JAR with verification.rmc.timing_fix.build.')
                pending = self.state['pending']
                if pending:
                    self.state['pending'] = None
                    atomic_json(self.state_path, self.state)
                    if stage != pending['stage'] or snapshot((*self.stage_inputs(stage), *self.contracts(stage))) != pending['inputs']:
                        raise ValueError('Stage inputs changed after the LLM request')
                    if args.agent_error:
                        with self.exp.attempt(stage, (*self.stage_inputs(stage), *self.contracts(stage))):
                            raise ValueError(args.agent_error)
                    self.import_response(stage, args.response, pending['inputs'])
                    status = 'executed'
                elif self.check_reuse(stage):
                    status = 'reused'
                    self.validate_output(stage, self.exp.folder)
                elif stage in LLM:
                    return self.request(stage)
                elif stage == 'rebeca_extraction':
                    self.managed(stage, rebeca_extractor._main, ['--input', str(self.model)])
                    status = 'executed'
                else:
                    self.managed(stage, verify_gate._main, ['--jar', str(self.jar)])
                    status = 'executed'

                self.record(stage, status)
                if stage == 'verification':
                    self.state['verification'] = self.verification_result()
                self.stages_current()
                atomic_json(self.state_path, self.state)
            except Exception as exc:
                self.state['stages'][stage] = {'status': 'failed'}
                if (stage == 'verification'
                        and self.exp.inspect()['stages'][stage].get('last_attempt') != prior_verification_attempt):
                    try:
                        self.state['verification'] = self.verification_result(failed=True)
                    except (OSError, ValueError, KeyError, ValidationError):
                        pass
                self.state['pending'] = None
                atomic_json(self.state_path, self.state)
                message = exc.message if isinstance(exc, ValidationError) else str(exc)
                return self.report('failed', {'stage': stage, 'message': message})
        return self.report('completed')

    def selection(self):
        return {'rule': self.exp.rule, 'rule_id': self.agent_id, 'mode': self.mode,
                'colreg': path_key(self.colreg), 'model': path_key(self.model), 'jar': path_key(self.jar)}

    def verification_result(self, *, failed=False):
        folder = self.exp.folder / 'verification'
        scratch = self.exp.work_root / 'verification' / ('failed' if failed else 'latest') / 'result'
        result = (scratch if failed else folder) / 'result.json'
        if not result.is_file():
            return None
        payload = read(result)
        self.validate_verification(payload)
        xml = folder / 'model_result.xml' if not failed else scratch / 'rmc/model_result.xml'
        if not xml.is_file() and not failed:
            path = payload['rmc_details'].get('result_artifact', {}).get('path')
            if path and Path(path).is_relative_to(scratch):
                xml = Path(path)
        summary = verification_summary(payload, xml)
        summary['result'] = path_key(result)
        summary['xml'] = path_key(xml) if xml.is_file() else None
        assessment = folder / 'assessment.md'
        if not failed and assessment.is_file():
            summary['assessment'] = path_key(assessment)
        output_dir = payload['rmc_details'].get('output_dir')
        logs = scratch / 'rmc' if failed or not output_dir else Path(output_dir)
        summary['logs'] = {name: path_key(logs / name) for name in
                           ('rmc_stdout.log', 'rmc_stderr.log', 'compile_stderr.log') if (logs / name).is_file()}
        workflow = scratch.parent / 'runner.stderr.log'
        if workflow.is_file() and (failed or logs == scratch / 'rmc'):
            summary['logs']['workflow'] = path_key(workflow)
        return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rule-id', '--rule', required=True)
    parser.add_argument('--colreg', type=Path)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--experiments-dir', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--reuse', action='store_true', help='Reuse current matching outputs (default)')
    mode.add_argument('--full-rerun', action='store_true', help='Execute every stage again')
    parser.add_argument('--resume', metavar='REQUEST_ID')
    response = parser.add_mutually_exclusive_group()
    response.add_argument('--response', type=Path)
    response.add_argument('--agent-error')
    parser.add_argument('--execution', choices=['native', 'same-session', 'external'], default='external')
    parser.add_argument('--input-tokens', type=int)
    parser.add_argument('--output-tokens', type=int)
    args = parser.parse_args(argv)
    if bool(args.resume) != bool(args.response or args.agent_error):
        parser.error('--resume requires --response or --agent-error and vice versa')
    if any(count is not None and count < 0 for count in (args.input_tokens, args.output_tokens)):
        parser.error('Token counts must be nonnegative')
    try:
        coordinator = Coordinator(args)
        coordinator.work.mkdir(parents=True, exist_ok=True)
        lock = coordinator.work / '.publish.lock'
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            result = coordinator.advance(args)
        finally:
            lock.unlink(missing_ok=True)
    except Exception as exc:
        result = {'status': 'failed', 'error': {'stage': 'coordinator_preflight', 'message': str(exc)}}
    print(json.dumps(result, indent=2))
    return int(result['status'] == 'failed')


if __name__ == '__main__':
    raise SystemExit(main())
