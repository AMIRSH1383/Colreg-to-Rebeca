"""Inspect freshness or import a completed COLREG extraction without an LLM call."""
import argparse
import json
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.utilities.experiment_store import Experiment, ROOT


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'publish-colreg'])
    parser.add_argument('--rule', required=True)
    parser.add_argument('--experiments-dir', type=Path)
    parser.add_argument('--source', type=Path, help='Actual saved agent JSON to import')
    parser.add_argument('--colreg-input', type=Path, help='Raw source if available; never inferred')
    args = parser.parse_args(argv)
    experiment = Experiment(args.rule, args.experiments_dir)
    if args.action == 'status':
        print(json.dumps(experiment.inspect(), indent=2))
        return 0
    if not args.source:
        parser.error('publish-colreg requires --source')
    import jsonschema
    inputs = [args.source] + ([args.colreg_input] if args.colreg_input else [])
    with experiment.attempt('colreg_extraction', inputs, provenance={
            'execution': 'import_existing_agent_response', 'raw_source_available': bool(args.colreg_input)}) as attempt:
        data = json.loads(args.source.read_text())
        jsonschema.validate(data, json.loads((ROOT / 'schemas/colreg-extractor.schema.json').read_text()))
        if data['status'] != 'ok':
            raise ValueError('Extraction is not successful')
        attempt.publish({'colreg_extraction.json': args.source})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
