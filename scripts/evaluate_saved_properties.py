"""Independent verification of already-generated properties; not an extraction backend.

This never supplies saved JSON as production pipeline input or substitutes for an
LLM call. Preserve and cite the originating inference artifacts separately.
"""
import argparse
import json
from pathlib import Path
from evaluate_direct_colreg import evaluate_ranges


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--oracle', choices=['A', 'B'], required=True)
    parser.add_argument('--jar', required=True)
    parser.add_argument('--wsl')
    parser.add_argument('--timeout', type=int, default=30)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = json.loads((args.run / 'report.json').read_text())
    # Copy only witness properties as evaluation inputs, never extraction JSON.
    for path in args.run.glob('applicability-*.property'):
        (args.output / path.name).write_bytes(path.read_bytes())
    result = evaluate_ranges(args.oracle, args.output, report,
        {'jar': args.jar, 'wsl': args.wsl, 'timeout': args.timeout}, True)
    result['originating_run'] = str(args.run)
    result['scope'] = 'Independent property checks of saved development inference; not a fresh frozen-cohort extraction'
    (args.output / 'report.json').write_text(json.dumps(result, indent=2))
    print(f"Property cases: {result.get('property_correct_cases', 0)}; RMC cases: {result.get('rmc_correct_cases', 0)} / {len(result['cases'])}")


if __name__ == '__main__':
    main()
