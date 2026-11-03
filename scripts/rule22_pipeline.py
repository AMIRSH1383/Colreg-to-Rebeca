"""Historical Milestone 1 regression runner, NOT the generic production pipeline.

Production entry point: scripts/direct_colreg.py (real LLM extraction).

No intermediate regulatory language is used. The built-in extraction is a closed
grammar for the supplied excerpt; --extraction-json accepts the existing agent's
schema. Inference is not secretly performed by either interface.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/rebeca_tooling/scripts'))
from extract_rebeca import extract, mask, blocks

CONCEPTS = ('masthead_light_range', 'sidelight_range', 'sternlight_range',
            'towing_light_range', 'all_round_light_range')
REVIEWED_NAMES = dict(zip(('vessel_length',) + CONCEPTS,
    ('ship_length', 'masthead_light_range', 'side_light_range', 'stern_light_range',
     'towing_light_range', 'allround_light_range')))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def extract_clause(source):
    """Fail closed on any wording outside this milestone's authoritative clause."""
    intro = ('The lights prescribed in these Rules shall have an intensity as specified in '
             'Section 8 Annex I to these Regulation so as to be visible at the following minimum ranges: ')
    scope = 'In vessels of 50 metres or more in length'
    phrases = ['a masthead light, 6 miles', 'a sidelight, 3 miles', 'a sternlight, 3 miles',
               'a towing light, 3 miles', 'a white, red, green or yellow all-round light, 3 miles']
    expected = intro + scope + ': -' + '; -'.join(phrases) + '.'
    if source.strip() != expected:
        raise ValueError('Built-in extractor only accepts the exact authoritative Rule22(a) excerpt; '
                         'supply schema-valid --extraction-json for an externally extracted clause')
    def statement(sid, role, quote, concept, value=None, unit=None, applies=None):
        return {'id': sid, 'role': role, 'source_text': quote, 'subjects': ['vessel'],
                'concept': concept, 'predicate': quote, 'operator': '>=' if value is not None else None,
                'value': value, 'unit': unit, 'applies_when': applies or []}
    statements = [statement('stmt01', 'obligation', intro.split(' so as')[0], 'light_intensity'),
                  statement('stmt02', 'scope', scope, 'vessel_length', 50, 'metres')]
    statements += [statement(f'stmt{i+3:02d}', 'obligation', phrase, concept, minimum,
                            'nautical_miles', ['stmt02'])
                   for i, (phrase, concept, minimum) in enumerate(zip(phrases, CONCEPTS, (6, 3, 3, 3, 3)))]
    return {'status': 'ok', 'rule_id': 'Rule-22a', 'extraction': {
        'entities': [{'id': 'vessel', 'name': 'vessel', 'type': 'participant', 'source_text': 'vessels'}],
        'statements': statements, 'references': ['Section 8 Annex I']},
        'open_assumptions': [{'source_text': intro.split(' so as')[0],
                              'reason': 'External intensity specification is outside this range experiment.'}]}


def validate_extraction(data, source):
    try:
        import jsonschema
    except ImportError as error:
        raise ValueError('jsonschema is required; see examples/rule22a/README.md') from error
    schema = json.loads((ROOT / 'schemas/colreg-extractor.schema.json').read_text())
    jsonschema.Draft202012Validator(schema).validate(data)
    if data['status'] != 'ok' or data['rule_id'] != 'Rule-22a':
        raise ValueError('Expected successful Rule-22a extraction')
    entities = data['extraction']['entities']
    statements = data['extraction']['statements']
    ids = [s['id'] for s in statements]
    entity_ids = [e['id'] for e in entities]
    if len(ids) != len(set(ids)) or len(entity_ids) != len(set(entity_ids)):
        raise ValueError('Duplicate statement/entity IDs')
    for item in entities + statements + data['open_assumptions']:
        if item['source_text'] not in source:
            raise ValueError('Ungrounded source quotation: ' + item['source_text'])
    for s in statements:
        if not set(s['subjects']) <= set(entity_ids) or not set(s['applies_when']) <= set(ids):
            raise ValueError('Dangling extraction reference')
    graph = {s['id']: s['applies_when'] for s in statements}
    def visit(node, trail):
        if node in trail:
            raise ValueError('Cyclic applicability dependencies')
        for parent in graph[node]:
            visit(parent, trail | {node})
    for node in graph:
        visit(node, set())
    # This executable milestone validates exact semantics, not just JSON shape.
    expected = extract_clause(source)
    actual = {s['concept']: s for s in statements}
    if len(actual) != len(statements) or set(actual) != {s['concept'] for s in expected['extraction']['statements']}:
        raise ValueError('Unexpected or missing Rule22 concepts')
    scope = actual['vessel_length']
    for wanted in expected['extraction']['statements']:
        found = actual[wanted['concept']]
        for key in ('role', 'operator', 'value', 'unit'):
            if found[key] != wanted[key]:
                raise ValueError('Rule22 semantic mismatch: ' + wanted['concept'] + '.' + key)
        parents = [scope['id']] if wanted['concept'] in CONCEPTS else []
        if found['applies_when'] != parents or found['subjects'] != ['vessel']:
            raise ValueError('Incorrect applicability/subjects')
    if 'Section 8 Annex I' not in data['extraction']['references']:
        raise ValueError('Missing Annex reference')
    return [{'statement_id': s['id'], 'start': source.index(s['source_text']),
             'end': source.index(s['source_text']) + len(s['source_text'])} for s in statements]


def bind(data, inventory):
    mapped, gaps = [], []
    actors = [a for a in inventory['reactive_classes'] if a['name'] == 'Ship']
    if len(actors) != 1:
        gaps.append({'concept': 'vessel', 'reason': 'Reviewed mapping requires exactly one Ship class'})
    instances = [i['name'] for i in inventory['instances'] if i['class'] == 'Ship']
    if not instances or len(set(instances)) != len(instances):
        gaps.append({'concept': 'vessel', 'reason': 'Missing or duplicate Ship instances'})
    variables = {v['name']: v['type'] for v in actors[0]['state_variables']} if len(actors) == 1 else {}
    if actors and len(variables) != len(actors[0]['state_variables']):
        gaps.append({'concept': 'model_structure', 'reason': 'Duplicate state-variable declarations'})
    for s in data['extraction']['statements']:
        if s['concept'] == 'light_intensity':
            continue
        name = REVIEWED_NAMES[s['concept']]
        if variables.get(name) != 'int':
            gaps.append({'statement_id': s['id'], 'concept': s['concept'],
                         'reason': f'Reviewed state variable Ship.{name} missing or not int',
                         'proposed_extension': 'Separately review a state variable and behavior with physical units; no automatic addition'})
        else:
            mapped.append({'statement_id': s['id'], 'concept': s['concept'], 'class': 'Ship',
                           'variable': name, 'type': 'int', 'unit': s['unit'],
                           'operator': s['operator'], 'value': s['value'],
                           'applies_when': s['applies_when'], 'instances': instances,
                           'mapping_basis': 'explicit reviewed Rule22 name table; no semantic guessing'})
    return {'status': 'blocked' if gaps else 'bound', 'mappings': mapped, 'gaps': gaps,
            'unresolved': [{'concept': 'light_intensity', 'reference': 'Section 8 Annex I',
                            'reason': 'External intensity semantics are not represented or verified'}],
            'unit_contract': {'ship_length': 'metres', 'range_fields': 'nautical_miles',
                             'status': 'declared experimental interpretation; not inferred from model types'},
            'full_regulatory_compliance': False}


def render(binding, witness_instance=None):
    if binding['status'] != 'bound':
        raise ValueError('Cannot synthesize unresolved range bindings')
    length = next(m for m in binding['mappings'] if m['concept'] == 'vessel_length')
    defines, assertions = [], []
    for instance in length['instances']:
        scope = f'M1_{instance}_scope'
        defines.append(f'{scope} = ({instance}.{length["variable"]} >= {length["value"]});')
        if witness_instance:
            if instance == witness_instance:
                assertions.append(f'M1_WitnessAbsent_{instance}: !{scope};')
            continue
        for m in binding['mappings']:
            if m['concept'] == 'vessel_length':
                continue
            ap = f'M1_{instance}_{m["concept"]}'
            defines.append(f'{ap} = ({instance}.{m["variable"]} >= {m["value"]});')
            assertions.append(f'M1_Range_{instance}_{m["concept"]}: !{scope} || {ap};')
    return defines, assertions


def merge_property(original, defines, assertions):
    """Insert into existing blocks without rewriting unrelated bytes/expressions."""
    if re.search(r'\bM1_\w+', mask(original)):
        raise ValueError('Reserved M1_ namespace already exists')
    clean = mask(original)
    outer = list(blocks(clean))
    if len(outer) != 1 or clean[:outer[0][1]].strip() != 'property':
        raise ValueError('Expected one property block')
    _, left, right = outer[0]
    body = clean[left+1:right]
    edits, seen, section_offsets = [], set(), {}
    for start, opening, closing in blocks(body):
        name = body[start:opening].strip()
        section_offsets[name] = left + 1 + start
        if name in ('define', 'Assertion'):
            if name in seen:
                raise ValueError('Duplicate property section')
            seen.add(name)
            items = defines if name == 'define' else assertions
            edits.append((left+1+closing, '\n    ' + '\n    '.join(items) + '\n  '))
    for name, items in (('define', defines), ('Assertion', assertions)):
        if name not in seen:
            offset = min(section_offsets.values(), default=right) if name == 'define' else min(
                (v for k, v in section_offsets.items() if k in ('TCTL', 'LTL')), default=right)
            edits.append((offset, '\n  ' + name + ' {\n    ' + '\n    '.join(items) + '\n  }\n'))
    grouped = {}
    for offset, insertion in edits:
        grouped[offset] = grouped.get(offset, '') + insertion
    for offset, insertion in sorted(grouped.items(), reverse=True):
        original = original[:offset] + insertion + original[offset:]
    return original


def fixture(length, ranges):
    fields = list(REVIEWED_NAMES.values())
    text = '// Experimental units: ship_length in metres; light ranges in nautical miles.\n'
    text += 'reactiveclass Ship(10) {\n  statevars {\n'
    text += ''.join(f'    int {name};\n' for name in fields)
    text += '  }\n  Ship() {\n'
    text += ''.join(f'    {name} = {value};\n' for name, value in zip(fields, [length] + ranges))
    text += '    self.check();\n  }\n  msgsrv check() { self.check(); }\n}\nmain { Ship s1():(); }\n'
    return text


def linux_path(path):
    value = str(Path(path).resolve())
    if re.match(r'^[A-Za-z]:', value):
        return '/mnt/' + value[0].lower() + value[2:].replace('\\', '/')
    return value


def verify(model, prop, output, args):
    output.mkdir(parents=True, exist_ok=False)
    details_path = output / 'details.json'
    tool = ROOT / 'skills/rebeca_tooling/scripts/run_rmc.py'
    paths = [tool, args.jar, model, prop, output, details_path]
    converted = [linux_path(p) if args.wsl else str(Path(p).resolve()) for p in paths]
    tool_path, jar, model_path, property_path, out, detail = converted
    command = [sys.executable, tool_path, '--jar', jar, '--model', model_path,
               '--property', property_path, '--output-dir', out, '--timeout-seconds', str(args.timeout),
               '--run-model-outcome', '--model-out-timeout-seconds', str(args.timeout),
               '--output-file', detail]
    if args.wsl:
        command[0] = 'python3'
        prefix = ['wsl', '-d', args.wsl, '--exec', 'env']
        if args.java_bin:
            prefix += ['PATH=' + linux_path(args.java_bin) + ':/usr/local/bin:/usr/bin:/bin']
        command = prefix + command
    started = time.perf_counter()
    record = {'verdict': 'unknown', 'command': command, 'details_path': str(details_path),
              'result_path': str(output / 'result.xml'), 'counterexample_path': None}
    try:
        process = subprocess.run(command, capture_output=True, timeout=args.timeout*3+15)
        (output / 'driver_stdout.log').write_bytes(process.stdout)
        (output / 'driver_stderr.log').write_bytes(process.stderr)
        record['driver_exit_code'] = process.returncode
        if details_path.is_file():
            details = json.loads(details_path.read_text())
            record['phase'] = details.get('rmc_outcome')
            record['verdict'] = details.get('verification_outcome', 'unknown')
        else:
            record['error'] = 'No structured execution details'
    except subprocess.TimeoutExpired:
        record.update(verdict='timeout', error='Outer execution budget exceeded')
    except OSError as error:
        record['error'] = str(error)
    # Independently read the fresh XML on the host; never trust process return codes.
    result = output / 'result.xml'
    if record['verdict'] in ('satisfied', 'cex'):
        from rmc_result_parser import parse_rmc_result_file
        parsed = parse_rmc_result_file(str(result), strict=True)
        record['raw_rmc_verdicts'] = parsed.get('raw_verdicts', [])
        if parsed['outcome'] != record['verdict']:
            record.update(verdict='unknown', error='Missing or inconsistent XML verdict')
        elif parsed.get('counterexample_path'):
            record['counterexample_path'] = parsed['counterexample_path']
        if record['verdict'] == 'cex':
            root = ET.parse(result).getroot()
            messages = [node.text for node in root.findall('./checked-property/message')]
            if not any(message and re.search(r'\b' + re.escape(message) + r'\s*:', prop.read_text()) for message in messages):
                record.update(verdict='unknown', error='Assertion failure does not identify a property in this experiment')
    record['elapsed_seconds'] = time.perf_counter() - started
    return record


def verify_pair(model, prop, binding, folder, args):
    result = {'verification': verify(model, prop, folder / 'verification', args), 'applicability': {}}
    length = next(m for m in binding['mappings'] if m['concept'] == 'vessel_length')
    if result['verification']['verdict'] not in ('satisfied', 'cex'):
        result['applicability'] = {instance: {'reachable': None, 'verdict': 'not_run',
            'reason': 'Baseline has no conclusive range verdict; avoid repeating a failed tool run'}
            for instance in length['instances']}
        result['vacuity_status'] = 'unknown'
        return result
    for instance in length['instances']:
        defines, assertions = render(binding, witness_instance=instance)
        witness = folder / f'applicability-{instance}.property'
        witness.write_text(merge_property('property { }', defines, assertions))
        check = verify(model, witness, folder / f'applicability-{instance}', args)
        check['reachable'] = True if check['verdict'] == 'cex' else False if check['verdict'] == 'satisfied' else None
        result['applicability'][instance] = check
    reach = [c['reachable'] for c in result['applicability'].values()]
    verdict = result['verification']['verdict']
    result['vacuity_status'] = ('unknown' if None in reach or verdict not in ('satisfied', 'cex')
        else 'not_satisfied' if verdict == 'cex' else 'vacuous' if False in reach else 'non_vacuous')
    return result


def run(args):
    started = time.perf_counter()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'milestone': 1, 'status': 'blocked', 'scope': 'Rule22(a) visibility ranges only',
              'input_paths': {'source': str(args.source), 'model': str(args.model),
                              'property': str(args.property) if args.property else None},
              'full_regulatory_compliance': False, 'inference': {
                  'llm_calls_this_run': 0, 'input_tokens': None, 'output_tokens': None,
                  'note': 'No inference invoked; external extraction usage is not available'},
              'cases': [], 'limitations': [
                  'Annex I intensity semantics are not verified.',
                  'Model field units are a declared experimental interpretation, not inferred facts.',
                  'Static scenario models are isolated tests, not a proven abstraction of navigation behavior.']}
    try:
        source = args.source.read_text(encoding='utf-8-sig').strip()
        report['source_clause'] = source
        report['input_hashes'] = {'source': digest(args.source), 'model': digest(args.model),
                                  'prompt': digest(ROOT / 'agents/colreg_extractor.md'),
                                  'schema': digest(ROOT / 'schemas/colreg-extractor.schema.json')}
        (args.output / 'source.txt').write_text(source + '\n', encoding='utf-8')
        data = json.loads(args.extraction_json.read_text()) if args.extraction_json else extract_clause(source)
        spans = validate_extraction(data, source)
        save(args.output / 'extraction.json', data)
        save(args.output / 'source-spans.json', spans)
        report['extraction'] = data
        report['extraction_method'] = 'external_schema_validated_json' if args.extraction_json else 'closed_rule22_grammar'
        inventory = extract(args.model.read_text(encoding='utf-8-sig'), str(args.model))
        save(args.output / 'inventory.json', inventory)
        binding = bind(data, inventory)
        save(args.output / 'binding.json', binding)
        report['binding'] = binding
        if binding['status'] != 'bound':
            raise ValueError('Required range semantics are missing; see binding.json; no variables added')
        model = args.output / 'model.rebeca'
        shutil.copyfile(args.model, model)
        original = args.property.read_bytes().decode('utf-8-sig') if args.property else 'property { }'
        if args.property:
            report['input_hashes']['property'] = digest(args.property)
        defines, assertions = render(binding)
        prop = args.output / 'model.property'
        prop.write_text(merge_property(original, defines, assertions), encoding='utf-8', newline='')
        report['generated_property_path'] = str(prop)
        report['model_preserved_byte_for_byte'] = digest(model) == digest(args.model)
        report['toolchain'] = {'jar': str(args.jar), 'jar_sha256': digest(args.jar) if args.jar.is_file() else None,
                               'wsl': args.wsl, 'java_bin': str(args.java_bin) if args.java_bin else None,
                               'per_phase_timeout_seconds': args.timeout}
        report['original_model'] = verify_pair(model, prop, binding, args.output / 'original', args)
        if args.scenarios:
            for length in (49, 50, 51):
                for broken in (None, 0, 1, 2, 3, 4):
                    ranges = [6, 3, 3, 3, 3]  # independent experimental oracle
                    if broken is not None:
                        ranges[broken] -= 1
                    name = f'length-{length}-' + ('compliant' if broken is None else f'below-{broken}')
                    folder = args.output / 'scenarios' / name
                    folder.mkdir(parents=True)
                    scenario_model = folder / 'model.rebeca'
                    scenario_model.write_text(fixture(length, ranges))
                    scenario_binding = bind(data, extract(scenario_model.read_text()))
                    scenario_prop = folder / 'model.property'
                    scenario_prop.write_text(merge_property('property { }', *render(scenario_binding)))
                    actual = verify_pair(scenario_model, scenario_prop, scenario_binding, folder, args)
                    expected = 'satisfied' if length == 49 or broken is None else 'cex'
                    reachable = actual['applicability']['s1']['reachable']
                    case = {'name': name, 'length_metres': length, 'ranges_nautical_miles': ranges,
                            'expected_verdict': expected, 'expected_applicable': length >= 50,
                            'model_path': str(scenario_model), 'property_path': str(scenario_prop), **actual}
                    case['passed'] = actual['verification']['verdict'] == expected and reachable == (length >= 50)
                    report['cases'].append(case)
                    save(folder / 'case.json', case)
                    print(name + ': ' + actual['verification']['verdict'] + ', applicability=' + str(reachable), flush=True)
        outcomes = report['original_model']['verification']['verdict']
        report['status'] = 'completed' if outcomes in ('satisfied', 'cex') else 'original_model_blocked'
        report['scenario_suite_passed'] = bool(report['cases']) and all(c['passed'] for c in report['cases'])
    except KeyboardInterrupt:
        report['status'] = 'interrupted'
        report['error'] = 'Execution interrupted; completed case artifacts retained; no unrun verdicts inferred'
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    report['elapsed_seconds'] = time.perf_counter() - started
    save(args.output / 'report.json', report)
    lines = ['# Direct Rule22(a) experiment', '', 'Status: ' + report['status'],
             'Scope: visibility ranges; full regulatory compliance is not established.',
             f"Elapsed: {report['elapsed_seconds']:.3f} seconds", '',
             f"Scenario cases: {len(report['cases'])}; passed: {sum(c['passed'] for c in report['cases'])}",
             '', 'Complete mappings, assumptions, execution logs, XML and trace paths: `report.json`.', '']
    if 'original_model' in report:
        lines += ['Submitted-model verdict: ' + report['original_model']['verification']['verdict'],
                  'Submitted-model vacuity: ' + report['original_model']['vacuity_status'], '']
    lines += ['| Case | Verdict | Applicable | Vacuity | Passed |', '| --- | --- | --- | --- | --- |']
    lines += [f"| {c['name']} | {c['verification']['verdict']} | {c['applicability']['s1']['reachable']} | {c['vacuity_status']} | {c['passed']} |" for c in report['cases']]
    if report.get('error'):
        lines += ['', report['error']]
    (args.output / 'report.md').write_text('\n'.join(lines) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'examples/rule22a/source.txt')
    parser.add_argument('--model', type=Path, default=ROOT / 'work/Original Model.rebeca')
    parser.add_argument('--property', type=Path)
    parser.add_argument('--extraction-json', type=Path)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--wsl', help='Existing WSL distribution, e.g. Ubuntu')
    parser.add_argument('--java-bin', type=Path, help='Java bin directory exposed inside WSL')
    parser.add_argument('--timeout', type=int, default=15)
    parser.add_argument('--scenarios', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'work/milestone1' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    result = run(args)
    print('Report: ' + str(args.output / 'report.json'))
    sys.exit(0 if result['status'] == 'completed' and (not args.scenarios or result.get('scenario_suite_passed')) else 1)


if __name__ == '__main__':
    main()
