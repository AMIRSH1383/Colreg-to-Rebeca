"""Isolated state-mutation check of a saved generated property, no new bindings."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from direct_colreg.verification import verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--field', required=True)
    parser.add_argument('--from-value', type=int, required=True)
    parser.add_argument('--to-value', type=int, required=True)
    parser.add_argument('--expected', choices=['VERIFIED', 'VIOLATED'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jar', required=True)
    parser.add_argument('--wsl')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z_]\w*', args.field):
        parser.error('Expected one scalar state-variable name')
    args.output.mkdir(parents=True, exist_ok=False)
    original = args.run / 'model.rebeca'
    text = original.read_text()
    pattern = r'\b' + re.escape(args.field) + r'\s*=\s*' + re.escape(str(args.from_value)) + r'\s*;'
    text, count = re.subn(pattern, args.field + ' = ' + str(args.to_value) + ';', text)
    if count != 1:
        raise ValueError('Expected exactly one initializer mutation')
    model = args.output / 'model.rebeca'
    model.write_text(text)
    prop = args.output / 'model.property'
    prop.write_bytes((args.run / 'model.property').read_bytes())
    result = verify(model, prop, args.output / 'verification',
                    {'jar': args.jar, 'wsl': args.wsl, 'timeout': 30})
    report = {'scope': 'State mutation of isolated saved model only; no extraction/binding replay',
        'originating_run': str(args.run), 'field': args.field,
        'from': args.from_value, 'to': args.to_value, 'expected': args.expected,
        'source_model_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
        'actual': result, 'passed': result['status'] == args.expected}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2))
    print('Mutation test passed: ' + str(report['passed']))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
