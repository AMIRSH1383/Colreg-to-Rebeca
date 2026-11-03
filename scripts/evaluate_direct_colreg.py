"""Frozen-implementation evaluation; expected answers never enter inference inputs."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from direct_colreg.pipeline import ROOT, run, save
from direct_colreg.verification import verify


def hashes():
    paths = list((ROOT / 'scripts/direct_colreg').glob('*.py')) + [
        ROOT / 'scripts/direct_colreg.py', ROOT / 'scripts/extract_colreg.py',
        ROOT / 'scripts/evaluate_direct_colreg.py', ROOT / 'agents/colreg_extractor.md',
        ROOT / 'agents/direct_semantic_contract.md', ROOT / 'schemas/colreg-extractor.schema.json',
        ROOT / 'schemas/colreg-semantic.schema.json', ROOT / 'configs/direct_provider.json',
        ROOT / 'configs/direct_model_catalog.json', ROOT / 'examples/rule22a/range-model.rebeca']
    paths += list((ROOT / 'skills/rebeca_tooling/scripts').glob('*.py'))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def freeze(output):
    output.mkdir(parents=True, exist_ok=False)
    diff = subprocess.run(['git', 'diff', '--binary'], cwd=ROOT, capture_output=True).stdout
    (output / 'tracked.diff').write_bytes(diff)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    manifest = {'timestamp': datetime.now(timezone.utc).isoformat(), 'git_head': head,
                'files': hashes(), 'note': 'Hash manifest includes untracked implementation; HEAD alone is insufficient'}
    save(output / 'manifest.json', manifest)
    for name in manifest['files']:
        target = output / 'snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    return manifest


def check_freeze(manifest):
    if hashes() != manifest['files']:
        raise RuntimeError('Frozen implementation/prompt/catalog/model changed; evaluation aborted')


def evaluate_boolean(text, names):
    text = text.replace('&&', ' and ').replace('||', ' or ')
    text = re.sub(r'!(?!=)', ' not ', text).strip()
    tree = ast.parse(text, mode='eval')
    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Name):
            return names[node.id] if node.id not in ('true', 'false') else node.id == 'true'
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not walk(node.operand)
        if isinstance(node, ast.BoolOp):
            values = [walk(n) for n in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        raise ValueError('Unexpected generated boolean syntax')
    return walk(tree)


def property_truth(text, state):
    names = {}
    for name, instance, field, op, value in re.findall(
            r'(\w+)\s*=\s*\((\w+)\.(\w+)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?|true|false)\);', text):
        right = value == 'true' if value in ('true', 'false') else float(value)
        left = state[field]
        names[name] = {'>': left > right, '>=': left >= right, '<': left < right,
                       '<=': left <= right, '==': left == right, '!=': left != right}[op]
    block = re.search(r'Assertion\s*\{([^}]*)\}', text, re.S)
    expressions = re.findall(r'\w+\s*:\s*([^;]+);', block[1]) if block else []
    if not expressions:
        raise ValueError('No generated assertions')
    return all(evaluate_boolean(e, names) for e in expressions)


def controlled_model(length, ranges):
    # Independent evaluator oracle: test-only fixture and expected field values.
    fields = ['ship_length', 'masthead_light_range', 'side_light_range',
              'stern_light_range', 'towing_light_range', 'allround_light_range']
    return ('reactiveclass Ship(10) { statevars { ' + ' '.join('int ' + f + ';' for f in fields)
        + ' } Ship() { ' + ' '.join(f'{f} = {v};' for f, v in zip(fields, [length] + ranges))
        + ' self.check(); } msgsrv check() { self.check(); } } main { Ship s1():(); }')


def evaluate_ranges(rule, output, report, config, real_checks):
    path = report.get('generated_property')
    if not path:
        return {'status': 'NO_GENERATED_PROPERTY', 'cases': []}
    text = Path(path).read_text()
    witnesses = sorted(output.glob('applicability-*.property'))
    cases = []
    # These expectations exist only in this evaluator, never in provider prompts,
    # production code or the model catalog.
    lengths = [49, 50, 51] if rule == 'A' else [11, 12, 19, 20, 49, 50]
    for length in lengths:
        minima = [6, 3, 3, 3, 3] if rule == 'A' else [3 if length < 20 else 5, 2, 2, 2, 2]
        applicable = length >= 50 if rule == 'A' else 12 <= length < 50
        for broken in (None, 0, 1, 2, 3, 4):
            ranges = minima.copy()
            if broken is not None:
                ranges[broken] -= 1
            name = f'{length}-' + ('compliant' if broken is None else str(broken))
            state = dict(zip(['ship_length', 'masthead_light_range', 'side_light_range',
                'stern_light_range', 'towing_light_range', 'allround_light_range'], [length] + ranges))
            expected = not applicable or broken is None
            item = {'name': name, 'expected_applicable': applicable, 'expected_satisfied': expected}
            try:
                item['generated_property_satisfied'] = property_truth(text, state)
                item['property_correct_on_state'] = item['generated_property_satisfied'] == expected
            except (ValueError, KeyError) as error:
                item['error'] = str(error)
                item['property_correct_on_state'] = False
            if real_checks:
                folder = output / 'boundary-cases' / name
                folder.mkdir(parents=True)
                model = folder / 'model.rebeca'
                model.write_text(controlled_model(length, ranges))
                check = verify(model, Path(path), folder / 'verification', config)
                item['rmc'] = check
                item['rmc_matches_expected'] = check['status'] == ('VERIFIED' if expected else 'VIOLATED')
                # Individual branch antecedents may be disjoint, so preserve
                # per-branch reachability rather than demand all branches active.
                item['applicability_checks'] = []
                for i, witness in enumerate(witnesses):
                    item['applicability_checks'].append(verify(model, witness, folder / f'witness-{i}', config))
            cases.append(item)
    return {'status': 'EVALUATED', 'cases': cases,
            'property_correct_cases': sum(c['property_correct_on_state'] for c in cases),
            'rmc_correct_cases': sum(c.get('rmc_matches_expected', False) for c in cases)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jar', required=True)
    parser.add_argument('--wsl')
    parser.add_argument('--timeout', type=int, default=30)
    parser.add_argument('--rmc-boundaries', action='store_true')
    parser.add_argument('--rule22b-source', type=Path)
    parser.add_argument('--only', nargs='*', help='Optional selected case IDs; freeze still includes all implementation')
    args = parser.parse_args()
    manifest = freeze(args.output / 'freeze')
    source_a = (ROOT / 'examples/rule22a/source.txt').read_text()
    # Synthetic robustness cases are clearly labeled, not asserted regulations.
    cases = [
        ('A', 'Rule-22a', source_a),
        ('A-whitespace', 'Rule-22a', source_a.replace(';', ';\n\n').replace(' -', '\n-')),
        ('A-paraphrase', 'Rule-22a-paraphrased', 'For vessels at least 50 metres long, minimum visibility ranges are: masthead light 6 nautical miles; sidelight, sternlight, towing light, and a white, red, green or yellow all-round light each 3 nautical miles. Required intensity is specified in Section 8 of Annex I.'),
        ('ambiguous', 'Synthetic-ambiguous', 'Every vessel shall proceed at a safe speed appropriate to the prevailing conditions.'),
        ('missing', 'Synthetic-missing', 'Every vessel shall maintain a battery temperature below 40 degrees Celsius.'),
        ('synthetic-supported', 'Synthetic-state-constraint', 'For vessels of at least 40 metres and less than 60 metres in length, the masthead light visibility range shall be greater than 5 nautical miles, unless the vessel length is below 45 metres.'),
        ('C', 'Rule-19', (ROOT / 'examples/milestone2/rule19.txt').read_text())]
    if args.rule22b_source:
        cases.insert(1, ('B', 'Rule-22b', args.rule22b_source.read_text()))
    config = {'jar': args.jar, 'wsl': args.wsl, 'timeout': args.timeout}
    summary = {'freeze': str(args.output / 'freeze/manifest.json'), 'results': [],
               'B': 'SOURCE_BLOCKED_PENDING_USER' if not args.rule22b_source else 'SCHEDULED'}
    for case_id, rule_id, source in cases:
        if args.only and case_id not in args.only:
            continue
        check_freeze(manifest)
        source_path = args.output / 'inputs' / (case_id + '.txt')
        source_path.parent.mkdir(exist_ok=True)
        source_path.write_text(source, encoding='utf-8')
        directory = args.output / case_id
        report = run(source_path, rule_id, ROOT / 'examples/rule22a/range-model.rebeca', directory,
            ROOT / 'configs/direct_provider.json', config, ROOT / 'configs/direct_model_catalog.json')
        check_freeze(manifest)
        entry = {'case': case_id, 'status': report['status'], 'stages': report['stages'],
                 'report': str(directory / 'report.json'), 'inference': report['inference'],
                 'semantic_review': 'PENDING_INDEPENDENT_REVIEW'}
        if case_id in ('A', 'B', 'A-whitespace', 'A-paraphrase'):
            evaluation = evaluate_ranges('B' if case_id == 'B' else 'A', directory, report, config,
                                         args.rmc_boundaries and case_id in ('A', 'B'))
            save(directory / 'independent-evaluation.json', evaluation)
            entry['property_evaluation'] = {k: v for k, v in evaluation.items() if k != 'cases'}
        summary['results'].append(entry)
        save(args.output / 'summary.json', summary)
        print(case_id + ': ' + report['status'], flush=True)
    usage = [c for r in summary['results'] for c in r['inference']['calls']]
    summary['cost_report'] = {'invocations': len(usage),
        'input_tokens': sum(c['input_tokens'] or 0 for c in usage),
        'output_tokens': sum(c['output_tokens'] or 0 for c in usage),
        'usage_complete': all(c['input_tokens'] is not None and c['output_tokens'] is not None for c in usage),
        'estimated_cost': sum(c['estimated_cost'] for c in usage) if usage and all(c['estimated_cost'] is not None for c in usage) else None,
        'inference_seconds': sum(c['latency_seconds'] for c in usage)}
    summary['freeze_unchanged'] = hashes() == manifest['files']
    summary['acceptance'] = 'NOT_ESTABLISHED: source availability and independent semantic review required'
    save(args.output / 'summary.json', summary)


if __name__ == '__main__':
    main()
