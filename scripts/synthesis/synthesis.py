#!/usr/bin/env python3
"""One-turn synthesis from saved contracts. Never verifies or changes inputs."""
from __future__ import annotations

# Permit both python -m and direct script invocation from any working directory.
import sys
from pathlib import Path
if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import jsonschema

try:
    from .apply_model_patches import apply_patches, digest
    from scripts.extraction.rebeca_extractor import mask_source, matching, parse_model
except ImportError:
    from apply_model_patches import apply_patches, digest
    from scripts.extraction.rebeca_extractor import mask_source, matching, parse_model

ROOT = Path(__file__).resolve().parents[2]
ID = r'[A-Za-z_][A-Za-z_0-9]*'
RULE22A_RANGE_FIELDS = {
    'masthead_light_range', 'side_light_range', 'stern_light_range',
    'towing_light_range', 'allround_light_range',
}
PRESCRIBED_LIGHT_ASSUMPTION = (
    'These symbolic range checks assume the checked lights are prescribed for the vessel. '
    'Legal applicability remains unresolved.'
)


def load(path):
    return json.loads(Path(path).read_text())


def unique(items, key):
    result = {x[key]: x for x in items}
    if len(result) != len(items):
        raise ValueError(f'Duplicate {key}')
    return result


def validate_binding(binding, colreg, model):
    """Validate the documented v1 contract without changing upstream schemas."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    require(set(binding) == {'status', 'rule_id', 'bindings', 'unresolved_concepts'}, 'Invalid binding root')
    require(binding['status'] in ('ok', 'partial'), 'Invalid binding status')
    require(binding['rule_id'] == colreg['rule_id'], 'Rule ID mismatch')
    statements = unique(colreg['extraction']['statements'], 'id')
    entities = unique(colreg['extraction']['entities'], 'id')
    classes = unique(model['reactive_classes'], 'name')
    instances = unique(model['instances'], 'name')
    expected = {('entity', e, None) for e in entities}
    expected |= {('concept', e, s['concept']) for s in statements.values() for e in s['subjects']}
    seen = set()
    for resolved, records in ((True, binding['bindings']), (False, binding['unresolved_concepts'])):
        require(isinstance(records, list), 'Binding records must be arrays')
        for record in records:
            base = {'kind', 'entity', 'concept', 'statement_ids', 'reason'}
            require(set(record) == base | ({'target', 'match_type', 'evidence', 'limitations'} if resolved else set()), 'Invalid binding record')
            key = record['kind'], record['entity'], record['concept']
            require(key in expected and key not in seen, 'Unknown or duplicate binding')
            seen.add(key)
            require(isinstance(record['reason'], str) and bool(record['reason'].strip()), 'Missing binding reason')
            ids = record['statement_ids']
            require(isinstance(ids, list) and len(ids) == len(set(ids)), 'Invalid statement IDs')
            expected_ids = {s['id'] for s in statements.values() if record['entity'] in s['subjects'] and (record['kind'] == 'entity' or s['concept'] == record['concept'])}
            require(set(ids) == expected_ids, 'Binding statement coverage mismatch')
            if not resolved:
                continue
            target = record['target']
            require(set(target) == {'class', 'instances', 'variable'}, 'Invalid binding target')
            require(target['class'] in classes, 'Unknown class')
            require(isinstance(target['instances'], list) and bool(target['instances']), 'Missing instances')
            require(len(target['instances']) == len(set(target['instances'])), 'Duplicate instances')
            for name in target['instances']:
                require(name in instances and instances[name]['class'] == target['class'], 'Unknown instance or class mismatch')
            require(set(target['instances']) == {i['name'] for i in instances.values() if i['class'] == target['class']}, 'Incomplete actor scope')
            fields = unique(classes[target['class']]['state_variables'], 'name')
            if record['kind'] == 'entity':
                require(target['variable'] is None, 'Entity target has variable')
            else:
                require(target['variable'] in fields, 'Unknown field')
                field = fields[target['variable']]
                require(not field['array_dimensions'] and field['type'] in ('int', 'byte', 'short', 'long', 'float', 'double', 'boolean'), 'Unsupported field type')
            require(record['match_type'] in ('exact', 'semantic'), 'Invalid match type')
            require(isinstance(record['limitations'], list) and all(isinstance(x, str) and x for x in record['limitations']), 'Invalid limitations')
            require(isinstance(record['evidence'], list) and bool(record['evidence']), 'Missing evidence')
            for evidence in record['evidence']:
                require(set(evidence) == {'input', 'pointer'} and evidence['input'] in ('colreg', 'rebeca'), 'Invalid evidence')
                value = colreg if evidence['input'] == 'colreg' else model
                require(isinstance(evidence['pointer'], str) and evidence['pointer'].startswith('/'), 'Invalid evidence pointer')
                try:
                    for part in evidence['pointer'].split('/')[1:]:
                        part = part.replace('~1', '/').replace('~0', '~')
                        value = value[int(part)] if isinstance(value, list) else value[part]
                except (KeyError, ValueError, IndexError, TypeError) as exc:
                    raise ValueError('Unresolvable evidence pointer') from exc
    require(seen == expected, 'Incomplete binding coverage')
    require(binding['status'] != 'ok' or not binding['unresolved_concepts'], 'Inconsistent binding status')
    for statement in statements.values():
        require(set(statement['subjects']) <= set(entities), 'Unknown subject')
        require(set(statement['applies_when']) <= set(statements), 'Unknown scope statement')
    return statements


def plan_requirements(colreg, binding, model):
    statements = validate_binding(binding, colreg, model)
    accepted = {(b['entity'], b['concept']): b for b in binding['bindings'] if b['kind'] == 'concept'}
    entity_bindings = {b['entity']: b for b in binding['bindings'] if b['kind'] == 'entity'}
    blocked = {}
    for sid, s in statements.items():
        reasons = []
        if s['role'] not in ('scope', 'condition', 'obligation', 'prohibition'):
            reasons.append('Unsupported statement role')
        if not s['subjects']:
            reasons.append('No participant scope')
        if s['operator'] not in ('>=', '>', '<=', '<', '==', '!=') or not isinstance(s['value'], (int, float, bool)):
            reasons.append('No supported scalar comparison')
        for subject in s['subjects']:
            b = accepted.get((subject, s['concept']))
            eb = entity_bindings.get(subject)
            if b is None or eb is None:
                reasons.append('Missing accepted concept or entity binding')
            else:
                if b['target']['class'] != eb['target']['class'] or b['target']['instances'] != eb['target']['instances']:
                    reasons.append('Concept and entity scopes differ')
                fields = {v['name']: v for c in model['reactive_classes'] if c['name'] == b['target']['class'] for v in c['state_variables']}
                is_bool = fields[b['target']['variable']]['type'] == 'boolean'
                if is_bool != isinstance(s['value'], bool) or (is_bool and s['operator'] not in ('==', '!=')):
                    reasons.append('Scalar comparison type mismatch')
        if reasons:
            blocked[sid] = list(dict.fromkeys(reasons))

    assumed_prerequisites = {}
    visited = set()

    def mapped_to(statement, fields):
        return all(accepted[subject, statement['concept']]['target']['class'] == 'Ship'
                   and accepted[subject, statement['concept']]['target']['variable'] in fields
                   for subject in statement['subjects'])

    def can_assume_prescription(sid, qualifier):
        statement, scope = statements[sid], statements[qualifier]
        if (colreg['rule_id'] != 'Rule-22a' or statement['role'] != 'obligation'
                or statement['operator'] != '>=' or statement['unit'] != 'miles'
                or not mapped_to(statement, RULE22A_RANGE_FIELDS)
                or ' '.join(scope['source_text'].casefold().split()).rstrip(' ,:;')
                != 'the lights prescribed in these rules'
                or scope['applies_when']
                or any(scope[key] is not None for key in ('operator', 'value', 'unit'))):
            return False
        return any(parent not in blocked
                   and (statements[parent]['operator'], statements[parent]['value'], statements[parent]['unit'])
                   == ('>=', 50, 'metres')
                   and mapped_to(statements[parent], {'ship_length'})
                   for parent in statement['applies_when'])

    def visit(sid, stack):
        if sid in visited:
            return
        if sid in stack:
            raise ValueError('Cyclic statement scope')
        for parent in statements[sid]['applies_when']:
            if statements[parent]['role'] not in ('scope', 'condition'):
                raise ValueError('Dependency must be scope or condition')
            if statements[parent]['subjects'] != statements[sid]['subjects']:
                raise ValueError('Cross-participant scope requires explicit semantics')
            visit(parent, stack | {sid})
        unresolved = [parent for parent in statements[sid]['applies_when'] if parent in blocked]
        # Preserve the statutory qualifier as an explicit external assumption.
        # This rule-specific projection still requires an executable length guard.
        if sid not in blocked and len(unresolved) == 1 and can_assume_prescription(sid, unresolved[0]):
            assumed_prerequisites[sid] = unresolved[0]
        elif unresolved:
            blocked.setdefault(sid, []).extend(f'Unresolved prerequisite {parent}' for parent in unresolved)
        visited.add(sid)
    for sid in statements:
        visit(sid, set())
    return statements, accepted, blocked, assumed_prerequisites


def semantic_caveats(colreg, binding, assumed_prerequisites):
    """Record uncertainty without interpreting free-text limitations as vetoes.

    Accepted scalar mappings permit symbolic checks, not established regulatory
    semantics. No model unit or conversion is asserted here.
    """
    records = binding['bindings']
    statements = {s['id']: s for s in colreg['extraction']['statements']}
    notes = {}
    def visit(sid):
        if sid in notes:
            return notes[sid]
        statement = statements[sid]
        own = [limitation for b in records if sid in b['statement_ids'] for limitation in b['limitations']]
        if sid in assumed_prerequisites:
            own.append(PRESCRIBED_LIGHT_ASSUMPTION)
        if statement['unit'] is not None:
            own.append(f"Regulatory interpretation requires established comparability with source unit {statement['unit']!r}; model units are unknown and no conversion is applied.")
        for assumption in colreg['open_assumptions']:
            # The upstream contract has no statement IDs for assumptions. Keep
            # unscoped assumptions visible for every candidate; never discard them.
            own.append('Unresolved extraction assumption: ' + assumption['reason'])
        for parent in statement['applies_when']:
            own.extend('Prerequisite ' + parent + ': ' + note for note in visit(parent))
        notes[sid] = list(dict.fromkeys(own))
        return notes[sid]
    for sid in statements:
        visit(sid)
    return {sid: values for sid, values in notes.items() if values}


def render_property(statements, bindings, generated, caveats=None, assumed_prerequisites=None):
    """Canonical state invariants; a scope condition is never asserted alone."""
    assumed_prerequisites = assumed_prerequisites or {}
    def comparison(sid, subject, actor):
        s = statements[sid]
        b = bindings[subject, s['concept']]['target']
        if actor not in b['instances']:
            raise ValueError('Incompatible prerequisite actor scope')
        literal = json.dumps(s['value'], allow_nan=False)
        expr = f"({actor}.{b['variable']} {s['operator']} {literal})"
        if s['role'] == 'prohibition':
            expr = f'!{expr}'
        return expr
    def guards(sid, subject, actor):
        parts = []
        for parent in statements[sid]['applies_when']:
            if parent == assumed_prerequisites.get(sid):
                continue
            parts += guards(parent, subject, actor) + [comparison(parent, subject, actor)]
        return list(dict.fromkeys(parts))
    assertions = []
    for sid in sorted(generated):
        s = statements[sid]
        for subject in s['subjects']:
            for actor in bindings[subject, s['concept']]['target']['instances']:
                expr = comparison(sid, subject, actor)
                conditions = guards(sid, subject, actor)
                if conditions:
                    expr = f"!({' && '.join(conditions)}) || {expr}"
                assertions.append(f'    {sid}_{subject}_{actor}: {expr};')
    if not assertions:
        return ''
    warning = ('// CONDITIONAL SYMBOLIC CHECKS ONLY: regulatory interpretation is unresolved.\n'
               '// Source thresholds are untranslated; model units and physical semantics are unestablished.\n'
               '// Qualifiers and assumptions require review in report.json; no compliance claim.\n') if any(sid in (caveats or {}) for sid in generated) else ''
    if generated & assumed_prerequisites.keys():
        warning += f'// {PRESCRIBED_LIGHT_ASSUMPTION}\n'
    return warning + 'property {\n  Assertion {\n' + '\n'.join(assertions) + '\n  }\n}\n'


def prepare(colreg, binding, source):
    model = parse_model(source.decode('utf-8'), '<input>')
    statements, accepted, blocked, assumed_prerequisites = plan_requirements(colreg, binding, model)
    text = source.decode('utf-8')
    lines = text.splitlines(keepends=True)
    selected = set()
    classes = {b['target']['class'] for b in binding['bindings']}
    for c in model['reactive_classes']:
        if c['name'] not in classes:
            continue
        for v in c['state_variables']:
            if any(b['target']['class'] == c['name'] and b['target']['variable'] == v['name'] for b in binding['bindings']):
                selected.add(v['line'])
                if 'constructor_initialization' in v:
                    selected.add(v['constructor_initialization']['line'])
    sections = []
    _, structure = mask_source(text)
    for match in re.finditer(r'\breactiveclass\s+(' + ID + r')\s*\([^)]*\)\s*\{', structure):
        if match[1] not in classes:
            continue
        end = matching(structure, structure.index('{', match.start(), match.end()), '{', '}')
        start = len(text[:end].encode('utf-8'))
        sections.append({'id': match[1] + ':observer', 'class': match[1], 'start': start, 'end': start + 1, 'sha256': digest(b'}'), 'text': '}', 'permission': 'insert pure boolean helper before closing brace only'})
    for i in model['instances']:
        if i['class'] in classes:
            selected.add(i['line'])
    caveats = semantic_caveats(colreg, binding, assumed_prerequisites)
    eligible = {sid for sid, s in statements.items() if sid not in blocked and s['role'] in ('obligation', 'prohibition')}
    request = {'colreg': colreg, 'binding': binding, 'source_sha256': digest(source),
               'source_lines': [{'line': n, 'text': lines[n - 1].rstrip('\r\n')} for n in sorted(selected)],
               'sections': sections, 'blocked': blocked, 'assumed_prerequisites': assumed_prerequisites,
               'semantic_uncertainties': caveats,
               'interpretation': 'symbolic candidates only where caveats are present; no inferred model units or behavior',
               'eligible_statements': sorted(eligible),
               'canonical_supported_property': render_property(statements, accepted, eligible, caveats, assumed_prerequisites)}
    return request, model


def validate_response(response, request, model):
    jsonschema.validate(response, load(ROOT / 'schemas/synthesis.schema.json'))
    statements, bindings, blocked, assumed_prerequisites = plan_requirements(request['colreg'], request['binding'], model)
    records = unique(response['requirements'], 'statement_id')
    if set(records) != set(statements):
        raise ValueError('Incomplete requirement dispositions')
    generated = set()
    for sid, record in records.items():
        disposition = record['disposition']
        if sid in blocked and disposition != 'unresolved':
            raise ValueError('Blocked requirement claimed supported')
        if disposition == 'generated':
            if sid not in request['eligible_statements']:
                raise ValueError('Unsupported generated requirement')
            generated.add(sid)
        if disposition == 'context' and (sid in blocked or statements[sid]['role'] not in ('scope', 'condition')):
            raise ValueError('Invalid context disposition')
    def validate_guard_dispositions(sid):
        for parent in statements[sid]['applies_when']:
            if parent == assumed_prerequisites.get(sid):
                continue
            if records[parent]['disposition'] != 'context':
                raise ValueError('Generated obligation requires context disposition for its guard')
            validate_guard_dispositions(parent)
    for sid in generated:
        validate_guard_dispositions(sid)
    unresolved = [r for r in records.values() if r['disposition'] == 'unresolved']
    if unresolved and not response['unresolved']:
        raise ValueError('Missing unresolved summary')
    if generated & assumed_prerequisites.keys() and PRESCRIBED_LIGHT_ASSUMPTION not in response['unresolved']:
        raise ValueError('Missing prescribed-light applicability assumption')
    if response['property_content'] != render_property(statements, bindings, generated, request['semantic_uncertainties'], assumed_prerequisites):
        raise ValueError('Property differs from validated comparisons, scopes, or actor coverage')
    sections = {s['id']: s for s in request['sections']}
    for patch in response['patches']:
        section = sections.get(patch['section_id'])
        if section is None or patch['old'] != '}':
            raise ValueError('Unauthorized patch')
        # Only observational, non-recursive helpers. No assignments, calls, or declarations.
        match = re.fullmatch(r'\s*boolean\s+(' + ID + r')\s*\(\s*\)\s*\{\s*return\s+([^;{}]+);\s*\}\s*\}', patch['new'])
        if not match:
            raise ValueError('Only pure observation helper insertion is permitted')
        cl = next(c for c in model['reactive_classes'] if c['name'] == section['class'])
        names = {v['name'] for v in cl['state_variables']} | {m['name'] for m in cl['helper_methods'] + cl['message_servers']}
        if match[1] in names or match[1] == cl['name']:
            raise ValueError('Observer name collision')
        expression = match[2].strip()
        # Helpers must observe an already-supported canonical predicate. This
        # excludes arbitrary expression syntax, invented thresholds and negation.
        permitted = set()
        for sid in generated:
            for subject in statements[sid]['subjects']:
                target = bindings[subject, statements[sid]['concept']]['target']
                if target['class'] != cl['name']:
                    continue
                statement = statements[sid]
                predicate = f"{target['variable']} {statement['operator']} {json.dumps(statement['value'], allow_nan=False)}"
                if statement['role'] == 'prohibition':
                    predicate = f'!({predicate})'
                permitted.add(predicate)
                canonical = render_property(statements, bindings, {sid}, assumed_prerequisites=assumed_prerequisites)
                for line in canonical.splitlines():
                    if ': ' in line:
                        local = line.split(': ', 1)[1].rstrip(';')
                        for actor in target['instances']:
                            local = local.replace(actor + '.', '')
                        permitted.add(local)
        if expression not in permitted:
            raise ValueError('Observer must use a supported canonical predicate')
    return generated


def invoke_codex(request, timeout, diagnostics_dir=None):
    """Single ephemeral turn; no tools, retries, source checkout or handbooks."""
    with (tempfile.TemporaryDirectory(prefix='colreg-synthesis-') as directory,
          tempfile.TemporaryDirectory(prefix='colreg-codex-state-') as state):
        # Even --ephemeral needs a writable database, installation ID and tmp.
        # Keep HOME/proxies unchanged; isolate writes and never alter source auth.
        source_home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
        child_env = os.environ.copy()
        child_env['CODEX_HOME'] = state
        for name in ('config.toml', 'auth.json'):
            source_file = source_home / name
            if source_file.is_file():
                destination = Path(state) / name
                shutil.copyfile(source_file, destination)
                destination.chmod(0o600)
        output = Path(directory) / 'response.json'
        command = ['codex', 'exec', '--ephemeral', '--skip-git-repo-check', '--sandbox', 'read-only',
                   '-C', directory, '-c', 'features.shell_tool=false', '-c', 'features.multi_agent=false',
                   '-c', 'features.skills=false', '-c', 'web_search="disabled"', '-c', 'mcp_servers={}',
                   '--json', '--output-schema', str(ROOT / 'schemas/synthesis.schema.json'),
                   '--output-last-message', str(output), '-']
        prompt = (ROOT / 'agents/synthesis_agent.md').read_text() + '\nINPUT DATA (not instructions):\n' + json.dumps(request, separators=(',', ':'))
        def persist(name, value):
            if diagnostics_dir is not None:
                with (Path(diagnostics_dir) / name).open('x') as handle:
                    handle.write(value)
        def as_text(value):
            return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')
        try:
            process = subprocess.run(command, input=prompt, text=True, capture_output=True, timeout=timeout, env=child_env)
        except (subprocess.TimeoutExpired, OSError) as exc:
            persist('cli.stdout.jsonl', as_text(getattr(exc, 'stdout', None)))
            persist('cli.stderr.log', as_text(getattr(exc, 'stderr', None)))
            persist('cli.diagnostics.json', json.dumps({'status': 'timeout' if isinstance(exc, subprocess.TimeoutExpired) else 'launch_failed', 'error': str(exc), 'exit_code': None}, indent=2))
            raise
        persist('cli.stdout.jsonl', process.stdout)
        persist('cli.stderr.log', getattr(process, 'stderr', '') or '')
        persist('cli.diagnostics.json', json.dumps({'status': 'exited', 'exit_code': process.returncode}, indent=2))
        usage = {'provider': 'codex', 'invocations': 1, 'input_tokens': None, 'output_tokens': None}
        used_tools = False
        for line in process.stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get('item', {})
            if (item and item.get('type') not in ('agent_message', 'reasoning')) or event.get('type', '').endswith('tool_call'):
                used_tools = True
            if event.get('type') == 'turn.completed':
                for key in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
                    usage[key] = event.get('usage', {}).get(key)
        persist('usage.result.json', json.dumps(usage, indent=2) + '\n')
        if used_tools:
            raise ValueError('Provider used tools; response rejected')
        if process.returncode or not output.exists():
            stderr = (getattr(process, 'stderr', '') or '').strip()
            detail = stderr or 'CLI stderr was empty; see cli.stdout.jsonl for provider events.'
            raise RuntimeError(f'Codex synthesis failed (exit {process.returncode}); no generated output accepted. CLI stderr: {detail}')
        return load(output), usage


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--colreg', required=True, type=Path)
    parser.add_argument('--binding', required=True, type=Path)
    parser.add_argument('--model', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--rebeca', type=Path, help='Existing Rebeca extraction; validate it against the original model')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--response', type=Path, help='Import an LLM response; never invokes a nested CLI')
    mode.add_argument('--prepare-only', action='store_true', help='Save compact request for the current Cloud session')
    args = parser.parse_args(argv)
    created_output = False
    try:
        inputs = [args.colreg, args.binding, args.model] + ([args.response] if args.response else []) + ([args.rebeca] if args.rebeca else [])
        missing = [str(p) for p in inputs if not p.is_file()]
        if missing:
            raise ValueError('Missing required input: ' + ', '.join(missing))
        out = args.output_dir.resolve()
        if out.exists():
            raise ValueError('Output directory already exists; refusing overwrite')
        if any(p.resolve().is_relative_to(out) for p in inputs):
            raise ValueError('Output directory contains an input')
        colreg, binding = load(args.colreg), load(args.binding)
        jsonschema.validate(colreg, load(ROOT / 'schemas/colreg-extractor.schema.json'))
        if colreg['status'] != 'ok':
            raise ValueError('COLREG extraction is not successful')
        source = args.model.read_bytes()
        request, model = prepare(colreg, binding, source)
        if args.rebeca:
            saved_model = load(args.rebeca)
            jsonschema.validate(saved_model, load(ROOT / 'schemas/rebeca_extraction.schema.json'))
            for key in ('schema_version', 'reactive_classes', 'instances', 'environment_constants'):
                if saved_model[key] != model[key]:
                    raise ValueError(f'Saved Rebeca extraction differs from original model: {key}')
        request['input_provenance'] = {str(path): digest(path.read_bytes()) for path in
                                       [args.colreg, args.binding, args.model] + ([args.rebeca] if args.rebeca else [])}
        # All preflight checks precede provider invocation and artifact creation.
        out.mkdir(parents=True, exist_ok=False)
        created_output = True
        def save(name, value):
            with (out / name).open('x') as handle:
                json.dump(value, handle, indent=2, allow_nan=False)
                handle.write('\n')
        save('request.json', request)
        if args.prepare_only:
            save('usage.json', {'invocations': 0, 'input_tokens': None, 'output_tokens': None})
            return 0
        usage = {'provider': 'external_response', 'invocations': 0, 'input_tokens': None, 'output_tokens': None}
        response = load(args.response)
        save('response.json', response)
        validate_response(response, request, model)
        result = apply_patches(source, request['source_sha256'], request['sections'], response['patches'])
        parse_model(result.decode('utf-8'), '<generated>')
        with (out / 'model.rebeca').open('xb') as handle:
            handle.write(result)
        # An empty property is NOT a valid or useful verification artifact.
        if response['property_content']:
            with (out / 'model.property').open('x') as handle:
                handle.write(response['property_content'])
        diff = ''.join(difflib.unified_diff(source.decode().splitlines(True), result.decode().splitlines(True), fromfile='original.rebeca', tofile='model.rebeca'))
        with (out / 'model.diff').open('x') as handle:
            handle.write(diff)
        save('patches.json', response['patches'])
        save('report.json', {'rule_id': colreg['rule_id'], 'status': 'partial' if request['semantic_uncertainties'] or any(r['disposition'] == 'unresolved' for r in response['requirements']) else 'generated',
                             'interpretation': request['interpretation'], 'semantic_uncertainties': request['semantic_uncertainties'],
                             'open_assumptions': colreg['open_assumptions'], 'references': colreg['extraction']['references'],
                             'requirements': response['requirements'], 'unresolved': response['unresolved'], 'blocked': request['blocked'],
                             'assumed_prerequisites': request['assumed_prerequisites'],
                             'binding_unresolved': binding['unresolved_concepts'], 'source_sha256': digest(source), 'model_sha256': digest(result),
                             'byte_identical': result == source, 'property_generated': bool(response['property_content']), 'verification': 'not_run', 'usage': usage})
        if not (out / 'usage.json').exists():
            save('usage.json', usage)
        elif not (out / 'usage.result.json').exists():
            save('usage.result.json', usage)
        return 0
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, subprocess.TimeoutExpired, jsonschema.ValidationError) as exc:
        if created_output:
            with (out / 'failure_report.json').open('x') as handle:
                json.dump({'status': 'execution_failed', 'error': str(exc), 'blocked': request['blocked'],
                           'semantic_uncertainties': request['semantic_uncertainties'], 'eligible_statements': request['eligible_statements'],
                           'verification': 'not_run'}, handle, indent=2)
        print(f'Synthesis failed: {exc}', file=sys.stderr)
        return 1


def main(argv=None):
    from scripts.utilities.stage_cli import managed_main
    return managed_main('synthesis', argv, _main)


if __name__ == '__main__':
    raise SystemExit(main())
