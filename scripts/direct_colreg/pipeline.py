"""Rule-independent orchestration from actual LLM output to checked state logic."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
from .provider import CodexProvider, ProviderError
from .semantics import ROOT, extraction_prompt, validate_extraction
from .binding import bind
from .synthesis import synthesize
from .agent_stages import handoff
from .logic import atoms, effective_applicability, property_text, Unsupported
from .property_io import merge
from .verification import verify
from extract_rebeca import extract


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')



def run(source_path, rule_id, model_path, output, provider_config, verification_config,
        catalog_path=None, property_path=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    config = json.loads(Path(provider_config).read_text())
    provider = CodexProvider(config['model'], config['timeout_seconds'], prices=config.get('prices'))
    report = {'rule_id': rule_id, 'status': 'UNKNOWN', 'full_source_verified': False,
        'stages': {'extraction': 'NOT_RUN', 'source_validation': 'NOT_RUN', 'binding': 'NOT_RUN',
                   'generation': 'NOT_RUN', 'rmc_execution': 'NOT_RUN'},
        'semantic_correctness': 'REQUIRES_INDEPENDENT_REVIEW', 'model_scope': 'submitted_model',
        'requirements': [], 'warnings': ['A checker verdict does not establish source interpretation correctness.']}
    try:
        source = Path(source_path).read_text(encoding='utf-8-sig')
        report['source'] = source
        report['hashes'] = {'source': digest(source_path), 'model': digest(model_path),
                            'provider_config': digest(provider_config)}
        shutil.copyfile(source_path, output / 'source.txt')
        schema = json.loads((ROOT / 'schemas/colreg-semantic.schema.json').read_text())
        data = provider.request(extraction_prompt(source, rule_id), schema, output / 'extraction-request', 'semantic_extraction')
        report['stages']['extraction'] = 'LLM_COMPLETED'
        save(output / 'extraction.json', data)
        report['stages']['source_validation'] = 'VALIDATING'
        spans = validate_extraction(data, source, rule_id)
        save(output / 'source-spans.json', spans)
        report['stages']['source_validation'] = 'PASSED'
        report['open_assumptions'] = data['open_assumptions']
        report['references'] = data['extraction']['references']
        inventory = extract(Path(model_path).read_text(encoding='utf-8-sig'), str(model_path))
        save(output / 'inventory.json', inventory)
        report['inventory_warnings'] = inventory['warnings']
        catalog = json.loads(Path(catalog_path).read_text()) if catalog_path else {'version': 1, 'models': [], 'mappings': []}
        if catalog_path:
            report['hashes']['catalog'] = digest(catalog_path)
        selected, candidates = bind(data, inventory, catalog, report['hashes']['model'], provider, output / 'binding-request')
        save(output / 'bindings.json', candidates)
        save(output / 'binding-handoff.json', handoff(data, selected, candidates, model_path, output / 'extraction.json'))
        report['binding_methods'] = {method: sum(r['method'] == method for r in candidates)
                                    for method in ('automatically_discovered', 'catalog_assisted', 'llm_assisted', 'manually_supplied', 'abstained')}
        report['stages']['binding'] = ('NOT_APPLICABLE' if not candidates else
            'RESOLVED' if all(r['selected'] for r in candidates) else 'PARTIAL_OR_UNRESOLVED')
        definitions, assertions, witnesses, records = synthesize(data, selected)
        report['requirements'] = records
        if not assertions:
            report['stages']['generation'] = 'UNSUPPORTED_SEMANTICS'
            report['status'] = 'UNSUPPORTED_SEMANTICS'
            return report
        model = output / 'model.rebeca'
        shutil.copyfile(model_path, model)
        original = Path(property_path).read_text(encoding='utf-8-sig') if property_path else 'property {}'
        prop = output / 'model.property'
        prop.write_text(merge(original, definitions, assertions), encoding='utf-8', newline='')
        report['model_preserved'] = digest(model) == digest(model_path)
        report['generated_property'] = str(prop)
        report['stages']['generation'] = 'GENERATED_SUPPORTED_SUBSET'
        result = verify(model, prop, output / 'verification', verification_config)
        report['verification'] = result
        report['stages']['rmc_execution'] = result['status']
        report['applicability'] = []
        for i, witness in enumerate(witnesses.values()):
            path = output / f'applicability-{i}.property'
            path.write_text(witness['text'])
            check = verify(model, path, output / f'applicability-{i}', verification_config)
            reachable = True if check['status'] == 'VIOLATED' else False if check['status'] == 'VERIFIED' else None
            if reachable:
                import xml.etree.ElementTree as ET
                labels = [n.text for n in ET.parse(check['result_path']).getroot().findall('./checked-property/message')]
                if 'G_WitnessAbsent' not in labels:
                    reachable = None
            report['applicability'].append({'requirements': witness['requirements'], 'instance': witness['instance'],
                                            'reachable': reachable, 'execution': check})
        reach = [r['reachable'] for r in report['applicability']]
        subset = result['status']
        if subset == 'VERIFIED':
            subset = 'UNKNOWN' if None in reach else 'VACUOUS' if False in reach else 'VERIFIED'
        report['supported_subset_status'] = subset
        report['status'] = 'UNSUPPORTED_SEMANTICS' if any(r['status'] != 'GENERATED' for r in records) else subset
        report['all_extracted_requirements_checked'] = report['status'] == 'VERIFIED' and not data['open_assumptions']
        # Checking every extracted predicate still does not establish correct or
        # complete source interpretation. Independent semantic review is separate.
        report['full_source_verified'] = False
    except ProviderError as error:
        report['error'] = str(error)
        report['blocker'] = 'PROVIDER_UNAVAILABLE_OR_FAILED'
    except (ValueError, KeyError, OSError, Unsupported) as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if report['stages']['source_validation'] == 'VALIDATING':
            report['stages']['source_validation'] = 'FAILED'
        report['inference'] = {'invocations': len(provider.calls), 'calls': provider.calls,
            'input_tokens': sum(c['input_tokens'] or 0 for c in provider.calls),
            'output_tokens': sum(c['output_tokens'] or 0 for c in provider.calls),
            'usage_complete': all(c['input_tokens'] is not None and c['output_tokens'] is not None for c in provider.calls),
            'estimated_cost': sum(c['estimated_cost'] for c in provider.calls) if provider.calls and all(c['estimated_cost'] is not None for c in provider.calls) else None,
            'inference_seconds': sum(c['latency_seconds'] for c in provider.calls)}
        report['elapsed_seconds'] = time.perf_counter() - started
        save(output / 'report.json', report)
    return report
