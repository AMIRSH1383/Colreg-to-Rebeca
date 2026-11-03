"""Reusable direct COLREG entry point: always performs real LLM extraction."""
import argparse
from pathlib import Path
from direct_colreg.pipeline import ROOT, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--rule-id', required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--property', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--provider-config', type=Path, default=ROOT / 'configs/direct_provider.json')
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--wsl')
    parser.add_argument('--timeout', type=int, default=30)
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error('Timeout must be positive')
    report = run(args.source, args.rule_id, args.model, args.output, args.provider_config,
                 {'jar': str(args.jar), 'wsl': args.wsl, 'timeout': args.timeout}, args.catalog, args.property)
    print(report['status'] + ': ' + str(args.output / 'report.json'))
    raise SystemExit(0 if report['status'] in ('VERIFIED', 'VACUOUS', 'VIOLATED') else 1)


if __name__ == '__main__':
    main()
