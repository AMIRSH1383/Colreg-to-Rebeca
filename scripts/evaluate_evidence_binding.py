"""Frozen Milestone 3 actual-inference binding tests and direct Rule22(a) rerun."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time
from direct_colreg.pipeline import ROOT, run, save
from direct_colreg.provider import CodexProvider
from direct_colreg.evidence_binding import bind_with_evidence
from direct_colreg.model_evidence import audit


def fingerprints():
    files = list((ROOT / 'scripts/direct_colreg').glob('*.py'))
    files += list((ROOT / 'skills/rebeca_tooling/scripts').glob('*.py'))
    files += [ROOT / name for name in ['scripts/direct_colreg.py', 'scripts/audit_model_semantics.py',
        'scripts/evaluate_evidence_binding.py', 'tests/test_evidence_binding.py',
        'agents/colreg_extractor.md', 'agents/direct_semantic_contract.md',
        'agents/semantic_binding_agent.md', 'agents/synthesis_agent.md', 'scripts/direct_agents.py',
        'schemas/colreg-semantic.schema.json', 'schemas/colreg-extractor.schema.json',
        'configs/direct_provider.json', 'configs/evidence_model_catalog.json',
        'configs/model_evidence_annotations.json', 'examples/rule22a/range-model.rebeca',
        'work/Original Model.rebeca', 'examples/rule22a/source.txt']]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jar', required=True)
    parser.add_argument('--wsl')
    parser.add_argument('--timeout', type=int, default=30)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    frozen = fingerprints()
    manifest = {'files': frozen, 'git_head': subprocess.run(['git', 'rev-parse', 'HEAD'],
        cwd=ROOT, capture_output=True, text=True).stdout.strip(),
        'note': 'Includes untracked source snapshots; not only HEAD. No changes allowed between cases.'}
    save(args.output / 'freeze/manifest.json', manifest)
    (args.output / 'freeze/tracked.diff').write_bytes(subprocess.run(['git', 'diff', '--binary'], cwd=ROOT, capture_output=True).stdout)
    for name in frozen:
        target = args.output / 'freeze/snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    spec = importlib.util.spec_from_file_location('independent_fixtures', ROOT / 'tests/test_evidence_binding.py')
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    config = json.loads((ROOT / 'configs/direct_provider.json').read_text())
    summary = {'binding_tests': [], 'confidence_threshold': 0.9, 'human_review': 'not_performed',
        'scope': 'Synthetic binding-only tests are separate from real regulatory extraction.'}
    for name, renamed, ambiguous, concept, expected in [
        ('positive', False, False, 'hull_length', 'q'),
        ('negative', False, False, 'ocean_depth', None),
        ('ambiguous', False, True, 'hull_length', None),
        ('renamed', True, False, 'hull_length', 'renamed_span')]:
        if fingerprints() != frozen:
            raise RuntimeError('Frozen implementation changed')
        folder = args.output / 'binding-tests' / name
        folder.mkdir(parents=True)
        catalog = fixtures.fixture(folder, renamed=renamed, ambiguous=ambiguous)
        save(folder / 'catalog.json', catalog)
        provider = CodexProvider(config['model'], config['timeout_seconds'])
        result = {'case': name, 'expected_variable': expected, 'selected_variable': None,
                  'passed': False, 'status': 'UNKNOWN'}
        try:
            selected, records = bind_with_evidence(fixtures.semantic_input(concept), fixtures.inventory(catalog),
                {'version': 2, 'models': [catalog]}, catalog['model_sha256'], provider, folder / 'request')
            save(folder / 'bindings.json', records)
            actual = next(iter(selected.values()))['variable'] if selected else None
            result.update(selected_variable=actual, passed=actual == expected, status='EVALUATED')
        except Exception as error:
            result['error'] = str(error)
        result['inference'] = provider.calls
        summary['binding_tests'].append(result)
        save(args.output / 'summary.json', summary)
        print(name + ': ' + str(result['passed']), flush=True)
    if fingerprints() != frozen:
        raise RuntimeError('Frozen implementation changed')
    report = run(ROOT / 'examples/rule22a/source.txt', 'Rule-22a', ROOT / 'examples/rule22a/range-model.rebeca',
        args.output / 'rule22a', ROOT / 'configs/direct_provider.json',
        {'jar': args.jar, 'wsl': args.wsl, 'timeout': args.timeout}, ROOT / 'configs/evidence_model_catalog.json')
    summary['rule22a'] = {'status': report['status'], 'stages': report['stages'],
        'supported_subset_status': report.get('supported_subset_status'),
        'binding_methods': report.get('binding_methods'), 'report': str(args.output / 'rule22a/report.json'),
        'full_source_verified': report['full_source_verified'], 'inference': report['inference']}
    # No inference needed to confirm that uncertain navigation-unit claims are
    # rejected before model matching. Actual declaration inventory is used.
    nav = audit(ROOT / 'work/Original Model.rebeca')
    catalogs = json.loads((ROOT / 'configs/evidence_model_catalog.json').read_text())
    from extract_rebeca import extract
    inventory = extract((ROOT / 'work/Original Model.rebeca').read_text(encoding='utf-8'))
    selected, records = bind_with_evidence(fixtures.semantic_input(), inventory, catalogs, nav['model_sha256'], None, None)
    save(args.output / 'navigation-binding.json', records)
    summary['navigation_unit_gate'] = {'selected': len(selected),
        'passed': not selected, 'scope': 'No unsupported unit/meaning claims promoted; not navigation verification'}
    summary['freeze_unchanged'] = fingerprints() == frozen
    summary['binding_tests_passed'] = all(r['passed'] for r in summary['binding_tests'])
    save(args.output / 'summary.json', summary)
    print('Rule22a subset: ' + str(report.get('supported_subset_status')), flush=True)


if __name__ == '__main__':
    main()
