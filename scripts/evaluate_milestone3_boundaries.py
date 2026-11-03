"""Independent Rule 22(a) oracle checks of frozen properties, never extraction input."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import time

from direct_colreg.verification import verify
from evaluate_evidence_binding import fingerprints


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jar', required=True)
    parser.add_argument('--wsl')
    parser.add_argument('--timeout', type=int, default=30)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    frozen = json.loads((args.run.parent / 'freeze/manifest.json').read_text())['files']
    if fingerprints() != frozen:
        raise ValueError('Generic implementation differs from originating frozen inference')
    original = (args.run / 'model.rebeca').read_text()
    prop = args.run / 'model.property'
    prop_hash = hashlib.sha256(prop.read_bytes()).hexdigest()
    config = {'jar': args.jar, 'wsl': args.wsl, 'timeout': args.timeout}
    # Independent oracle only: these answers are never given to the production binder.
    ranges = {'masthead_light_range': 6, 'side_light_range': 3,
              'stern_light_range': 3, 'towing_light_range': 3,
              'allround_light_range': 3}
    jobs = []
    for length in (49, 50, 51):
        for broken in (None, *ranges):
            name = str(length) + '-' + (broken or 'compliant')
            folder = args.output / name
            folder.mkdir()
            values = {'ship_length': length, **ranges}
            if broken:
                values[broken] -= 1
            text = original
            for field, value in values.items():
                text, count = re.subn(r'\b' + field + r'\s*=\s*\d+\s*;',
                                     field + ' = ' + str(value) + ';', text)
                if count != 1:
                    raise ValueError('Expected exactly one isolated fixture initializer: ' + field)
            model = folder / 'model.rebeca'
            model.write_text(text)
            # Frozen extraction abstained on all-round color scope. Its absence
            # must be recorded as coverage failure, never counted as compliance.
            covered = broken != 'allround_light_range'
            expected = 'VIOLATED' if length >= 50 and broken and covered else 'VERIFIED'
            jobs.append((name, model, prop, folder, expected, covered, length, broken))
        # Applicability depends only on length in this frozen property; check once
        # per length on a compliant fixture, independently of obligation verdicts.
        folder = args.output / (str(length) + '-reachability')
        folder.mkdir()
        model = args.output / (str(length) + '-compliant/model.rebeca')
        jobs.append((str(length) + '-reachability', model,
                     args.run / 'applicability-0.property', folder,
                     'VIOLATED' if length >= 50 else 'VERIFIED', True, length, None))
    started = time.perf_counter()

    def execute(job):
        name, model, property_path, folder, expected, covered, length, broken = job
        actual = verify(model, property_path, folder / 'verification', config)
        result = {'case': name, 'length_metres': length, 'violating_field': broken,
                  'kind': 'reachability' if name.endswith('reachability') else 'obligation',
                  'covered_by_frozen_property': covered, 'expected_checker_status': expected,
                  'actual': actual, 'matches_expected_checker_status': actual['status'] == expected}
        (folder / 'report.json').write_text(json.dumps(result, indent=2))
        print(name + ': ' + actual['status'], flush=True)
        return result

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(execute, jobs))
    witnesses = {r['length_metres']: r['actual']['status'] for r in results
                 if r['kind'] == 'reachability'}
    for result in results:
        if result['kind'] != 'obligation':
            continue
        witness = witnesses[result['length_metres']]
        result['applicability_reachable'] = (True if witness == 'VIOLATED' else
                                           False if witness == 'VERIFIED' else None)
        actual = result['actual']['status']
        result['subset_status'] = ('VACUOUS' if actual == 'VERIFIED' and witness == 'VERIFIED'
                                   else 'UNKNOWN' if actual == 'VERIFIED' and witness != 'VIOLATED'
                                   else actual)
        if not result['covered_by_frozen_property']:
            result['regulatory_requirement_status'] = 'UNSUPPORTED_SEMANTICS'
        (args.output / result['case'] / 'report.json').write_text(json.dumps(result, indent=2))
    unchanged = fingerprints() == frozen and hashlib.sha256(prop.read_bytes()).hexdigest() == prop_hash
    summary = {'originating_run': str(args.run), 'cases': results,
               'scope': 'Frozen generated subset only; all-round omissions remain coverage gaps',
               'elapsed_seconds': time.perf_counter() - started, 'llm_calls': 0,
               'frozen_implementation_and_property_unchanged': unchanged,
               'matching_checker_cases': sum(r['matches_expected_checker_status'] for r in results),
               'uncovered_mutations': sum(not r['covered_by_frozen_property'] for r in results),
               'full_rule_verified': False}
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2))
    raise SystemExit(0 if unchanged and all(r['matches_expected_checker_status'] for r in results) else 1)


if __name__ == '__main__':
    main()
