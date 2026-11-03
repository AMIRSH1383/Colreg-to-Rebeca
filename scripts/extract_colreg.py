"""Real LLM extraction CLI. No rule-specific parsing or replay mode."""
import argparse
import json
from pathlib import Path
from direct_colreg.provider import CodexProvider
from direct_colreg.semantics import ROOT, extraction_prompt, validate_extraction


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--rule-id', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--provider-config', type=Path, default=ROOT / 'configs/direct_provider.json')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    config = json.loads(args.provider_config.read_text())
    provider = CodexProvider(config['model'], config['timeout_seconds'], prices=config.get('prices'))
    source = args.source.read_text(encoding='utf-8-sig')
    schema = json.loads((ROOT / 'schemas/colreg-semantic.schema.json').read_text())
    try:
        data = provider.request(extraction_prompt(source, args.rule_id), schema, args.output / 'provider', 'semantic_extraction')
        spans = validate_extraction(data, source, args.rule_id)
        (args.output / 'extraction.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
        (args.output / 'spans.json').write_text(json.dumps(spans, indent=2), encoding='utf-8')
    finally:
        (args.output / 'usage.json').write_text(json.dumps(provider.calls, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
