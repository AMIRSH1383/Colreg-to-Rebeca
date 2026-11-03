"""Run binding and synthesis separately using direct COLREG extraction artifacts."""
import argparse
import json
from pathlib import Path
from direct_colreg.semantics import ROOT, validate_extraction
from direct_colreg.provider import CodexProvider
from direct_colreg.binding import bind
from direct_colreg.agent_stages import handoff, validate_handoff, write_synthesis
from extract_rebeca import extract


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['bind', 'synthesize'])
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--extraction', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--catalog', type=Path)
    p.add_argument('--binding', type=Path)
    p.add_argument('--property', type=Path)
    p.add_argument('--provider-config', type=Path, default=ROOT / 'configs/direct_provider.json')
    args = p.parse_args()
    if args.stage == 'bind' and not args.catalog:
        p.error('Binding requires an evidence catalog; unknown meanings must remain unresolved')
    if args.stage == 'synthesize' and not args.binding:
        p.error('Synthesis requires a binding handoff')
    args.output.mkdir(parents=True, exist_ok=False)
    data = json.loads(args.extraction.read_text(encoding='utf-8'))
    validate_extraction(data, args.source.read_text(encoding='utf-8-sig'), data['rule_id'])
    inventory = extract(args.model.read_text(encoding='utf-8-sig'), str(args.model))
    if args.stage == 'bind':
        config = json.loads(args.provider_config.read_text())
        provider = CodexProvider(config['model'], config['timeout_seconds'], prices=config.get('prices'))
        catalog = json.loads(args.catalog.read_text())
        from direct_colreg.agent_stages import digest
        try:
            selected, records = bind(data, inventory, catalog, digest(args.model), provider, args.output / 'request')
            result = handoff(data, selected, records, args.model, args.extraction)
            (args.output / 'binding.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        finally:
            (args.output / 'usage.json').write_text(json.dumps(provider.calls, indent=2), encoding='utf-8')
        print('Binding artifact: ' + str(args.output / 'binding.json'))
    else:
        artifact = json.loads(args.binding.read_text(encoding='utf-8'))
        selected = validate_handoff(artifact, inventory, args.model, args.extraction)
        result = write_synthesis(data, selected, args.model, args.output, args.property)
        print(result['status'] + ': ' + str(args.output / 'synthesis.json'))


if __name__ == '__main__':
    main()
