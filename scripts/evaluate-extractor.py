"""Reproducible, bounded structural and downstream Rule22 extractor evaluation."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/rebeca_tooling/scripts'))
from extract_rebeca import extract


def compact(value):
    return re.sub(r'\s+', '', value)


def facts(inventory):
    result = []
    for actor in inventory['reactive_classes']:
        name = actor['name']
        result.append(('class', name, actor['queue_capacity']))
        for category in ('state_variables', 'known_rebecs'):
            result.extend((category, name, v['name'], v['type']) for v in actor[category])
        result.extend(('message', name, m['name'], compact(m['parameters']))
                      for m in actor['message_servers'])
    result.extend(('instance', i['name'], i['class'], compact(i['known_rebec_arguments']),
                   compact(i['constructor_arguments'])) for i in inventory['instances'])
    return Counter(result)


def reference_facts(reference):
    result = []
    for name, actor in reference['classes'].items():
        result.append(('class', name, actor['queue_capacity']))
        for category in ('state_variables', 'known_rebecs'):
            result.extend((category, name, variable, kind)
                          for kind, names in actor[category].items() for variable in names)
        result.extend(('message', name, method, compact(parameters))
                      for method, parameters in actor['message_servers'].items())
    result.extend(('instance', name, args[0], compact(args[1]), compact(args[2]))
                  for name, args in reference['instances'].items())
    return Counter(result)


def compare(inventory, reference):
    actual, expected = facts(inventory), reference_facts(reference)
    correct = sum((actual & expected).values())
    assignments = []
    for name, actor in reference['classes'].items():
        matching = [c for c in inventory['reactive_classes'] if c['name'] == name]
        found = [(a['variable'], compact(a['expression'])) for c in matching
                 for ctor in c['constructors'] for a in ctor['assignments']]
        for variable, expression in actor['selected_assignments'].items():
            assignments.append({'class': name, 'variable': variable,
                                'expected_expression': expression,
                                'passed': found.count((variable, compact(expression))) == 1})
    return {'precision': correct / sum(actual.values()) if actual else 0,
            'recall': correct / sum(expected.values()) if expected else 0,
            'expected_facts': sum(expected.values()), 'correct_facts': correct,
            'missing': list((expected - actual).elements()),
            'unexpected': list((actual - expected).elements()),
            'selected_assignments': assignments,
            'passed': actual == expected and all(a['passed'] for a in assignments)}


def bind(inventory, mapping):
    actors = [a for a in inventory['reactive_classes'] if a['name'] == mapping['class']]
    if len(actors) != 1:
        raise ValueError('Binding requires exactly one matching reactive class')
    variables = {v['name']: v['type'] for v in actors[0]['state_variables']}
    for name in [mapping['length_variable']] + [r['variable'] for r in mapping['requirements']]:
        if variables.get(name) != 'int':
            raise ValueError('Missing or incorrectly typed binding variable: ' + name)
    instances = [i['name'] for i in inventory['instances'] if i['class'] == mapping['class']]
    if not instances or len(instances) != len(set(instances)):
        raise ValueError('Binding requires distinct matching instances')
    return instances


def properties(inventory, mapping):
    lines = ['property {', '  Assertion {']
    for instance in bind(inventory, mapping):
        for requirement in mapping['requirements']:
            lines.append(f"    Rule22_{instance}_{requirement['concept']}: "
                         f"({instance}.{mapping['length_variable']} < {mapping['length_minimum']}) || "
                         f"({instance}.{requirement['variable']} >= {requirement['minimum']});")
    return '\n'.join(lines + ['  }', '}', ''])


def evaluate_property(text, state):
    """Interpret only our emitted implication grammar, never arbitrary Python."""
    expressions = re.findall(r':\s*\((\w+\.\w+) < (\d+)\) \|\| \((\w+\.\w+) >= (\d+)\);', text)
    if len(expressions) != text.count('Rule22_') or not expressions:
        raise ValueError('Unsupported property expression')
    return all(state[left] < int(limit) or state[right] >= int(minimum)
               for left, limit, right, minimum in expressions)


def scenarios(inventory, mapping, output):
    # Independent experimental oracle: deliberately not taken from binding minima.
    minimums = [6, 3, 3, 3, 3]
    results = []
    for length in (49, 50, 51):
        for broken in (None, 0, 1, 2, 3, 4):
            ranges = minimums.copy()
            if broken is not None:
                ranges[broken] -= 1
            name = f"length_{length}_" + ('compliant' if broken is None else f'below_{broken}')
            directory = output / name
            directory.mkdir(parents=True, exist_ok=True)
            fields = [mapping['length_variable']] + [r['variable'] for r in mapping['requirements']]
            # Small static projection, not a behavioral abstraction proof of original model.
            model = 'reactiveclass Ship(10) {\n  statevars {\n'
            model += ''.join(f'    int {field};\n' for field in fields)
            model += '  }\n  Ship() {\n'
            model += ''.join(f'    {field} = {value};\n' for field, value in zip(fields, [length] + ranges))
            model += '  }\n}\nmain {\n'
            model += ''.join(f'  Ship {instance}():();\n' for instance in bind(inventory, mapping))
            model += '}\n'
            (directory / 'model.rebeca').write_text(model, encoding='utf-8')
            scenario_inventory = extract(model)
            property_text = properties(scenario_inventory, mapping)
            (directory / 'model.property').write_text(property_text, encoding='utf-8')
            state = {f'{instance}.{field}': value for instance in bind(scenario_inventory, mapping)
                     for field, value in zip(fields, [length] + ranges)}
            expected = length == 49 or broken is None
            observed = evaluate_property(property_text, state)
            results.append({'name': name, 'applicable': length >= 50,
                            'expected_satisfied': expected, 'static_satisfied': observed,
                            'passed': observed == expected,
                            'rmc': {'status': 'not_run'}})
    return results


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def run(output, jar=None):
    output.mkdir(parents=True, exist_ok=True)
    source = (ROOT / 'work/Original Model.rebeca').read_text(encoding='utf-8-sig')
    reference = json.loads((ROOT / 'tests/evaluation/original_model_reference.json').read_text())
    mapping = json.loads((ROOT / 'tests/evaluation/rule22_binding.json').read_text())
    rule_path = ROOT / mapping['source']
    rule_source = rule_path.read_text(encoding='utf-8-sig')
    if not all(r['source_text'] in rule_source for r in mapping['requirements']):
        raise ValueError('Binding quotations do not match rule source')
    inventory = extract(source, 'work/Original Model.rebeca')
    write_json(output / 'inventory.json', inventory)
    generated = properties(inventory, mapping)
    (output / 'model.property').write_text(generated, encoding='utf-8')
    write_json(output / 'binding.json', mapping)
    expected = (ROOT / 'tests/evaluation/rule22_expected.property').read_text()
    cases = scenarios(inventory, mapping, output / 'scenarios')
    rmc_status = 'not_run: pass --rmc-jar to request real verification'
    if jar:
        missing = [tool for tool in ('java', 'g++') if not shutil.which(tool)]
        if not jar.is_file():
            missing.append(str(jar))
        if missing:
            rmc_status = 'unavailable: ' + ', '.join(missing)
        else:
            from run_rmc import run_rmc_detailed
            rmc_status = 'attempted'
            for case in cases:
                directory = output / 'scenarios' / case['name']
                rmc_directory = Path(tempfile.mkdtemp(prefix='rmc-', dir=directory))
                details = run_rmc_detailed(str(jar.resolve()), str((directory / 'model.rebeca').resolve()),
                    str((directory / 'model.property').resolve()), str(rmc_directory.resolve()),
                    timeout_seconds=60, run_model_outcome=True,
                    model_out_export_result='result.xml')
                write_json(directory / 'rmc-details.json', details)
                # Never accept Java/compile failure or exit-code-only classifications as a verdict.
                artifact = details.get('result_artifact', {})
                verdict = artifact.get('outcome', 'unknown')
                valid = (details.get('rmc_exit_code') == 0 and details.get('cpp_compile_ok')
                         and details.get('model_out', {}).get('executed')
                         and artifact.get('parsed') and verdict in ('satisfied', 'cex'))
                case['rmc'] = {'status': verdict if valid else 'error_or_unknown',
                               'passed': bool(valid and (verdict == 'satisfied') == case['expected_satisfied'])}
    structural = compare(inventory, reference)
    report = {'source_sha256': inventory['source_sha256'],
              'rule_sha256': hashlib.sha256(rule_source.encode()).hexdigest(),
              'reference_provenance': reference['provenance'], 'reference_scope': reference['scope'],
              'structural': structural,
              'property_matches_reference': compact(generated) == compact(expected),
              'scenario_count': len(cases), 'scenarios': cases, 'rmc_status': rmc_status,
              'extractor_warnings': inventory['warnings'],
              'limitations': ['Reference fixtures need independent human review.',
                  'Static checks interpret emitted predicates; they are not model checking.',
                  'Scenarios are static projections; original-model behavior is not verified.',
                  'Bindings and rule thresholds are explicit fixtures, not LLM-generated semantics.',
                  'Precision and recall apply only to the declared reference scope.']}
    report['local_passed'] = bool(structural['passed'] and report['property_matches_reference']
                                  and all(c['passed'] for c in cases))
    report['rmc_passed'] = bool(rmc_status == 'attempted' and all(c['rmc'].get('passed') for c in cases))
    write_json(output / 'report.json', report)
    markdown = ['# Extractor evaluation', '', f"Local checks passed: {report['local_passed']}",
        f"Structural precision: {structural['precision']:.3f}; recall: {structural['recall']:.3f}",
        f"Correct structural facts: {structural['correct_facts']}/{structural['expected_facts']}",
        f"Property reference match: {report['property_matches_reference']}",
        f"Static scenarios passed: {sum(c['passed'] for c in cases)}/{len(cases)}",
        f'Real RMC: {rmc_status}', f"Real RMC checks passed: {report['rmc_passed']}", '',
        '| Scenario | Applicable | Expected satisfied | Static satisfied | RMC |',
        '| --- | --- | --- | --- | --- |']
    markdown += [f"| {c['name']} | {c['applicable']} | {c['expected_satisfied']} | {c['static_satisfied']} | {c['rmc']['status']} |" for c in cases]
    markdown += ['', '## Scope and limitations', '', reference['scope'], '']
    markdown += ['- ' + item for item in report['limitations']]
    (output / 'report.md').write_text('\n'.join(markdown) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'work/evaluation')
    parser.add_argument('--rmc-jar', type=Path)
    args = parser.parse_args()
    result = run(args.output_dir.resolve(), args.rmc_jar)
    print(f"Report: {args.output_dir / 'report.md'}")
    print(f"Local checks: {result['local_passed']}; RMC: {result['rmc_status']}")
    sys.exit(0 if result['local_passed'] and (not args.rmc_jar or result['rmc_passed']) else 1)
