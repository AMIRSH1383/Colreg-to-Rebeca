"""Produce reproducible lexical evidence and optional source-cited semantic catalog."""
import argparse
import json
from pathlib import Path
from direct_colreg.model_evidence import build_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', action='append', type=Path, required=True)
    parser.add_argument('--annotations', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite an existing catalog')
    annotations = json.loads(args.annotations.read_text())['annotations'] if args.annotations else []
    catalog = build_catalog(args.model, annotations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2), encoding='utf-8')
    print('Audited fields: ' + str(sum(len(m['fields']) for m in catalog['models'])))


if __name__ == '__main__':
    main()
