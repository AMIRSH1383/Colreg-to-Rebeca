"""Evidence-preserving candidate filtering and optional bounded LLM selection."""
import json
import re
from .logic import atoms, check_type, Unsupported

SELECTION_SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['selections'],
    'properties': {'selections': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
        'required': ['key', 'selected', 'evidence', 'confidence'], 'properties': {
            'key': {'type': 'string'}, 'selected': {'type': ['string', 'null']},
            'evidence': {'type': 'string'}, 'confidence': {'type': ['number', 'null']}}}}}}


def normalized(value):
    return re.sub(r'[^a-z0-9]', '', value.lower())


def bind(data, inventory, catalog, model_hash, provider, directory):
    if catalog.get('version') == 2:
        from .evidence_binding import bind_with_evidence
        return bind_with_evidence(data, inventory, catalog, model_hash, provider, directory)
    if catalog.get('version') != 1:
        raise ValueError('Unsupported catalog version')
    metadata = {}
    for entry in catalog.get('models', []):
        if entry['sha256'] == model_hash:
            metadata = {(f['class'], f['variable']): f for f in entry['fields']}
    fields = []
    for actor in inventory['reactive_classes']:
        for variable in actor['state_variables']:
            info = metadata.get((actor['name'], variable['name']))
            fields.append({'id': actor['name'] + '.' + variable['name'], 'class': actor['name'],
                           'variable': variable['name'], 'type': variable['type'],
                           'unit': info['unit'] if info else None,
                           'unit_known': info is not None or variable['type'] == 'boolean',
                           'description': info.get('description') if info else None,
                           'metadata_provenance': info.get('provenance') if info else None})
    comparisons = {}
    for requirement in data['formalization']:
        if requirement['support'] != 'state' or requirement['temporal'] is not None:
            continue
        for expr in [requirement['applicability'], requirement['obligation']] + requirement['exceptions']:
            for atom in atoms(expr):
                comparisons.setdefault((atom['entity'], atom['concept']), []).append(atom)
    entities = {e['id']: e for e in data['extraction']['entities']}
    records, pending, selected = [], [], {}
    for (entity, concept), uses in comparisons.items():
        candidates, rejected = [], []
        for field in fields:
            reason = None
            try:
                for use in uses:
                    check_type(use, field['type'])
                    if not field['unit_known'] or use['unit'] != field['unit']:
                        raise Unsupported('Units unknown or incompatible; no inferred conversions')
            except Unsupported as error:
                reason = str(error)
            if reason:
                rejected.append({'candidate': field['id'], 'reason': reason})
            else:
                item = dict(field)
                item['name_overlap'] = len(set(re.findall(r'[a-z]+', concept.lower())) &
                                           set(re.findall(r'[a-z]+', field['variable'].lower())))
                candidates.append(item)
        key = entity + ':' + concept
        record = {'key': key, 'entity': entity, 'concept': concept, 'candidates': candidates,
                  'rejected_candidates': rejected, 'selected': None, 'method': 'abstained',
                  'evidence': None, 'confidence': None}
        # Catalog mappings must be explicitly reviewed and tied to this model.
        reviewed = [r for r in catalog.get('mappings', []) if r['model_sha256'] == model_hash
                    and r['entity'] == entity and r['concept'] == concept]
        matches = [c for c in candidates if any(r['field'] == c['id'] for r in reviewed)]
        exact = [c for c in candidates if normalized(c['variable']) == normalized(concept)
                 and normalized(c['class']) in (normalized(entity), normalized(entities[entity]['name']))]
        if len(matches) == 1 and len(reviewed) == 1:
            record.update(selected=matches[0]['id'], method=reviewed[0].get('method', 'catalog_assisted'),
                          evidence=reviewed[0]['evidence'])
        elif len(exact) == 1:
            record.update(selected=exact[0]['id'], method='automatically_discovered',
                          evidence='Exact concept and actor identity plus independently supplied type/unit metadata')
        elif candidates:
            pending.append({'key': key, 'entity': entities[entity], 'concept': concept,
                'statements': [s for s in data['extraction']['statements'] if s['concept'] == concept],
                'candidates': candidates})
        records.append(record)
    if pending and provider:
        prompt = ('Select only genuinely equivalent model fields from the supplied finite candidates. '
                  'Do not use tools or files. Names or substring overlap alone are insufficient. '
                  'Related states are not interchangeable; do not substitute a weaker predicate. '
                  'Abstain with selected null when equivalence is not established. Include source/model evidence. '
                  'Confidence is a self-report, not calibrated probability. No new identifiers are allowed.\n'
                  + json.dumps(pending))
        response = provider.request(prompt, SELECTION_SCHEMA, directory, 'semantic_binding')
        choices = response['selections']
        seen = set()
        for choice in choices:
            key = choice['key']
            if key in seen or key not in {r['key'] for r in pending}:
                raise ValueError('Binding provider returned unknown or duplicate key')
            seen.add(key)
            record = next(r for r in records if r['key'] == key)
            if choice['selected'] is not None:
                if choice['selected'] not in {c['id'] for c in record['candidates']} or not choice['evidence']:
                    raise ValueError('Invented/unsupported model selection')
                if choice['confidence'] is None or not 0.9 <= choice['confidence'] <= 1:
                    record['evidence'] = 'Abstained: self-reported confidence below policy threshold; not calibrated'
                else:
                    record.update(selected=choice['selected'], evidence=choice['evidence'],
                                  confidence=choice['confidence'], method='llm_assisted')
            else:
                record['evidence'] = choice['evidence']
    for record in records:
        if record['selected']:
            field = next(c for c in record['candidates'] if c['id'] == record['selected'])
            instances = [i['name'] for i in inventory['instances'] if i['class'] == field['class']]
            if not instances:
                record.update(selected=None, method='abstained', evidence='No actual class instances')
            else:
                selected[(record['entity'], record['concept'])] = {**field, 'instances': instances,
                    'method': record['method']}
    return selected, records
