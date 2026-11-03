"""General schema/source validation; no regulatory thresholds or known answers."""
import json
from pathlib import Path
from .logic import atoms, validate, Unsupported

ROOT = Path(__file__).resolve().parents[2]


def extraction_prompt(source, rule_id):
    legacy = (ROOT / 'agents/colreg_extractor.md').read_text(encoding='utf-8')
    interface = (ROOT / 'agents/direct_semantic_contract.md').read_text(encoding='utf-8')
    return legacy + '\n\n' + interface + '\n\nINPUT DATA:\n' + json.dumps({'rule_id': rule_id, 'source': source})


def validate_extraction(data, source, rule_id):
    import jsonschema
    schema = json.loads((ROOT / 'schemas/colreg-semantic.schema.json').read_text())
    jsonschema.Draft202012Validator(schema).validate(data)
    original = {k: data[k] for k in ('status', 'rule_id', 'extraction', 'open_assumptions')}
    jsonschema.validate(original, json.loads((ROOT / 'schemas/colreg-extractor.schema.json').read_text()))
    if data['rule_id'] != rule_id:
        raise ValueError('Provider changed rule identifier')
    entities = data['extraction']['entities']
    statements = data['extraction']['statements']
    ids = [s['id'] for s in statements]
    entity_ids = [e['id'] for e in entities]
    if len(set(ids)) != len(ids) or len(set(entity_ids)) != len(entity_ids):
        raise ValueError('Duplicate semantic IDs')
    spans = []
    for item in entities + statements + data['open_assumptions']:
        quote = item['source_text']
        if not quote or quote not in source:
            raise ValueError('Quotation not grounded in supplied source: ' + quote)
        spans.append({'id': item.get('id'), 'quote': quote, 'start': source.index(quote),
                      'end': source.index(quote) + len(quote)})
    graph = {s['id']: s['applies_when'] for s in statements}
    for s in statements:
        if not set(s['subjects']) <= set(entity_ids) or not set(s['applies_when']) <= set(ids):
            raise ValueError('Dangling source dependency')
    def visit(node, trail):
        if node in trail:
            raise ValueError('Cyclic source dependency')
        for child in graph[node]:
            visit(child, trail | {node})
    for node in graph:
        visit(node, set())
    req_ids = [r['id'] for r in data['formalization']]
    if len(set(req_ids)) != len(req_ids):
        raise ValueError('Duplicate requirement IDs')
    covered = set()
    for r in data['formalization']:
        if not set(r['statement_ids']) <= set(ids):
            raise ValueError('Requirement lacks source statement')
        covered.update(r['statement_ids'])
        if r['support'] != 'state':
            if not r['reason']:
                raise ValueError('Abstention requires a reason')
            continue
        for expression in [r['applicability'], r['obligation']] + r['exceptions']:
            validate(expression)
            for atom in atoms(expression):
                if atom['entity'] not in entity_ids:
                    raise ValueError('Logical expression invents actor')
                # Require the exact compare to occur in an extracted statement;
                # shape/source checks still do not establish semantic correctness.
                matches = [s for s in statements if s['concept'] == atom['concept']
                           and atom['entity'] in s['subjects'] and s['operator'] == atom['operator']
                           and type(s['value']) is type(atom['value']) and s['value'] == atom['value']
                           and s['unit'] == atom['unit']]
                if not matches:
                    raise ValueError('Formal comparison has no extracted supporting statement')
    missing = [s['id'] for s in statements if s['role'] in ('obligation', 'prohibition') and s['id'] not in covered]
    if missing:
        raise ValueError('Normative statements omitted from formalization: ' + ', '.join(missing))
    return spans
