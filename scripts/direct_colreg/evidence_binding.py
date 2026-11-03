"""Evidence-constrained generic binding, separate from preserved v1 behavior."""
import json
import re
from pathlib import Path
from .logic import atoms, check_type, Unsupported
from .model_evidence import validate_field, validate_citation
from extract_rebeca import mask

SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['selections'],
    'properties': {'selections': {'type': 'array', 'items': {'type': 'object',
        'additionalProperties': False, 'required': ['key', 'selected', 'evidence', 'confidence', 'citations'],
        'properties': {'key': {'type': 'string'}, 'selected': {'type': ['string', 'null']},
            'evidence': {'type': 'string'}, 'confidence': {'type': ['number', 'null']},
            'citations': {'type': 'array', 'items': {'type': 'string'}}}}}}}


def evidence_id(e):
    return e['sha256'][:16] + ':' + str(e['line_start']) + ':' + str(e['line_end'])


def bind_with_evidence(data, inventory, catalog, model_hash, provider, directory):
    models = [m for m in catalog['models'] if m['model_sha256'] == model_hash]
    if len(models) != 1:
        raise ValueError('Evidence catalog must identify exactly one hash-matched model')
    model = models[0]
    real = {(a['name'], v['name']): v['type'] for a in inventory['reactive_classes'] for v in a['state_variables']}
    fields, rejected_fields = [], []
    for field in model['fields']:
        key = (field['class'], field['variable'])
        if real.get(key) != field['type']:
            raise ValueError('Evidence catalog declaration disagrees with actual inventory')
        valid = validate_field(field, model_hash)
        item = {'id': '.'.join(key), 'class': field['class'], 'variable': field['variable'],
                'type': field['type'], 'unit': field['unit'], 'unit_status': field['unit_status'],
                'description': field['description'], 'kind': field['kind'],
                'suitability': field['suitability'], 'review_status': field['review_status'],
                'contradictions': field['contradictions'], 'evidence': [],
                'no_operational_reads': not bool(field['reads']),
                'write_members': sorted({w['member'] for w in field['writes']})}
        # Actual source context supplements semantic evidence; a lexical match
        # does not establish field ownership, a read/write, or a physical unit.
        item['usage_context'] = []
        actor = next(a for a in inventory['reactive_classes'] if a['name'] == field['class'])
        for context in actor.get('source_context', []):
            lines = context['source'].splitlines()
            for index, line in enumerate(mask(context['source']).splitlines()):
                if re.search(r'\b' + re.escape(field['variable']) + r'\b', line):
                    item['usage_context'].append({'member': context['member'],
                        'line': context['line_start'] + index, 'source': lines[index],
                        'certainty': 'lexical occurrence; check parameter/local shadowing'})
        for e in field['semantic_evidence'] + field['declarations']:
            item['evidence'].append({'id': evidence_id(e), **e})
        item['declaration_ids'] = [evidence_id(e) for e in field['declarations']]
        item['semantic_ids'] = [evidence_id(e) for e in field['semantic_evidence']]
        item['documentary_ids'] = [evidence_id(e) for e in field['semantic_evidence']
                                   if re.search(r'//|/\*', e['quote'])]
        if valid:
            fields.append(item)
        else:
            rejected_fields.append({'candidate': item['id'], 'reason': 'Meaning/units uncertain, contradictory, or outside configured-attribute scope',
                                    'unit_status': field['unit_status'], 'contradictions': field['contradictions']})
    comparisons = {}
    for requirement in data['formalization']:
        if requirement['support'] != 'state' or requirement['temporal'] is not None:
            continue
        for expr in [requirement['applicability'], requirement['obligation']] + requirement['exceptions']:
            for atom in atoms(expr):
                comparisons.setdefault((atom['entity'], atom['concept']), []).append(atom)
    entities = {e['id']: e for e in data['extraction']['entities']}
    records, requests, selected = [], [], {}
    for (entity, concept), uses in comparisons.items():
        candidates, rejected = [], list(rejected_fields)
        for field in fields:
            try:
                for use in uses:
                    check_type(use, field['type'])
                    if use['unit'] != field['unit']:
                        raise Unsupported('Incompatible source-supported units; no implicit conversion')
                candidates.append(field)
            except Unsupported as error:
                rejected.append({'candidate': field['id'], 'reason': str(error)})
        record = {'key': entity + ':' + concept, 'entity': entity, 'concept': concept,
                  'candidates': candidates, 'rejected_candidates': rejected,
                  'selected': None, 'method': 'abstained', 'evidence': None, 'confidence': None,
                  'citations': [], 'review_status': 'not_human_reviewed',
                  'scope': 'configured attributes of the exact submitted model, not physical regulatory compliance'}
        records.append(record)
        if candidates:
            requests.append({'key': record['key'], 'entity': entities[entity], 'concept': concept,
                'statements': [s for s in data['extraction']['statements'] if s['concept'] == concept],
                'candidates': candidates})
    if requests and provider:
        prompt = ('Match source concepts to actual model fields using the supplied source-cited model audit. '
            'Do not use tools, files, external examples, regulatory thresholds as hints, or unseen variables. '
            'Names alone are insufficient. Combine documented attribute family, declared field/category, physical unit, '
            'ownership, constructor assignments and operational reads/writes. Source documentation may explicitly '
            'define a family of configured attributes rather than repeating each definition. This supports only '
            'configured-attribute checks, never a claim of measured physical performance. '
            'No human review is implied. Distinguish documented configuration from sensor measurement, derived state '
            'or physical realization. Do not map behavioral capability onto a constant flag. '
            'Select only when the finite evidence establishes equivalence within that stated scope. '
            'Cite at least the declaration and relevant documentary evidence IDs belonging to the selected field. '
            'If two candidates are semantically indistinguishable, abstain; do not use initializer values to break ties. '
            'If documentation, units, ownership or meaning is uncertain, select null. Confidence is uncalibrated.\n'
            + json.dumps(requests))
        contract = (Path(__file__).resolve().parents[2] / 'agents/semantic_binding_agent.md').read_text(encoding='utf-8')
        response = provider.request(' '.join(contract.splitlines()) + ' ' + prompt, SCHEMA, directory, 'evidence_semantic_binding')
        seen = set()
        for choice in response['selections']:
            if choice['key'] in seen or choice['key'] not in {r['key'] for r in records}:
                raise ValueError('Unknown/duplicate evidence binding key')
            seen.add(choice['key'])
            record = next(r for r in records if r['key'] == choice['key'])
            record['evidence'] = choice['evidence']
            record['confidence'] = choice['confidence']
            if choice['selected'] is None:
                continue
            matches = [c for c in record['candidates'] if c['id'] == choice['selected']]
            if len(matches) != 1:
                raise ValueError('Selected variable is not a validated candidate')
            field = matches[0]
            ids = set(choice['citations'])
            valid_ids = {e['id'] for e in field['evidence']}
            valid_citations = (ids <= valid_ids and ids & set(field['declaration_ids']) and
                              ids & set(field['documentary_ids']))
            if not valid_citations or not choice['evidence']:
                record['evidence'] = 'Rejected selection: declaration and documentary citations are required'
                continue
            if choice['confidence'] is None or not 0.9 <= choice['confidence'] <= 1:
                record['evidence'] = 'Abstained: unchanged confidence threshold 0.9 not met'
                continue
            indistinguishable = [c for c in record['candidates'] if c['description'] == field['description']
                                  and c['unit'] == field['unit'] and c['class'] == field['class']]
            if len(indistinguishable) > 1:
                record['evidence'] = 'Abstained: multiple fields share indistinguishable documented meaning'
                continue
            instances = [i['name'] for i in inventory['instances'] if i['class'] == field['class']]
            if not instances:
                continue
            record.update(selected=field['id'], method='llm_assisted', citations=choice['citations'])
            selected[(record['entity'], record['concept'])] = {**field, 'instances': instances,
                'method': 'llm_assisted', 'evidence_citations': choice['citations']}
    return selected, records
