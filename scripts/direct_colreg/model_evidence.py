"""Bounded, source-cited state-variable audit. No regulation or expected binding input.

This is lexical def/use evidence, not a data-flow proof. Local shadowing is flagged
and such occurrences are not silently treated as state reads/writes.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'skills/rebeca_tooling/scripts'))
from extract_rebeca import extract, mask, blocks, declarations


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def citation(path, source, start, end=None):
    lines = source.splitlines()
    end = start if end is None else end
    return {'path': str(path), 'sha256': sha(path), 'line_start': start, 'line_end': end,
            'quote': '\n'.join(lines[start-1:end])}


def validate_citation(evidence, model_hash=None):
    path = Path(evidence['path'])
    if not path.is_absolute():
        path = ROOT / path
    if sha(path) != evidence['sha256'] or model_hash and evidence['sha256'] != model_hash:
        raise ValueError('Evidence source hash mismatch')
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    start, end = evidence['line_start'], evidence['line_end']
    if not 1 <= start <= end <= len(lines) or '\n'.join(lines[start-1:end]) != evidence['quote']:
        raise ValueError('Evidence quotation/line mismatch')
    return True


def audit(model):
    model = Path(model).resolve()
    source = model.read_text(encoding='utf-8-sig')
    clean = mask(source)
    inventory = extract(source, str(model))
    by_class = {a['name']: a for a in inventory['reactive_classes']}
    fields = []
    for prefix, opening, closing in blocks(clean):
        header = clean[prefix:opening]
        match = re.search(r'\breactiveclass\s+(\w+)', header)
        if not match:
            continue
        name = match[1]
        body = clean[opening+1:closing]
        members = []
        for start, left, right in blocks(body):
            signature = body[start:left].strip()
            signature = re.sub(r'^@priority\s*\([^()]*\)\s*', '', signature)
            member_name = re.search(r'(\w+)\s*\(', signature)
            parameters = re.search(r'\((.*?)\)', signature, re.S)
            params = set(re.findall(r'\b(\w+)\s*(?:,|$)', parameters[1])) if parameters else set()
            members.append({'start': opening+1+start, 'left': opening+1+left,
                            'right': opening+1+right, 'signature': signature,
                            'name': member_name[1] if member_name else signature, 'parameters': params})
        for variable in by_class[name]['state_variables']:
            occurrences, shadowed = [], []
            for occurrence in re.finditer(r'\b' + re.escape(variable['name']) + r'\b', body):
                absolute = opening+1+occurrence.start()
                line = source.count('\n', 0, absolute)+1
                member = next((m for m in members if m['start'] <= absolute <= m['right']), None)
                if not member:
                    continue
                evidence = citation(model, source, line)
                context = member['name']
                declared = member['signature'] == 'statevars'
                local_text = clean[member['left']+1:member['right']]
                local_declaration = re.search(r'\b(?:int|byte|short|double|float|boolean)\s+(?:\[[^]]+\]\s*)*' + re.escape(variable['name']) + r'\b', local_text)
                is_shadowed = not declared and (variable['name'] in member['parameters'] or local_declaration)
                tail = clean[absolute+len(variable['name']):]
                write = bool(re.match(r'\s*(?:\[[^]]+\]\s*)*(?:=(?!=)|[+*/%-]=|\+\+|--)', tail))
                role = 'declaration' if declared else 'write' if write else 'read'
                entry = {'role': role, 'member': context, 'evidence': evidence}
                if is_shadowed:
                    entry['reason'] = 'Possible local/parameter shadowing; not attributed to state'
                    shadowed.append(entry)
                else:
                    occurrences.append(entry)
            writes = [o for o in occurrences if o['role'] == 'write']
            reads = [o for o in occurrences if o['role'] == 'read']
            transitions = [o for o in writes if o['member'] != name]
            kind = 'mutable_state' if transitions else 'constructor_configured_attribute' if writes else 'uninitialized_or_unresolved'
            fields.append({'class': name, 'variable': variable['name'], 'type': variable['type'],
                'instances': [i for i in inventory['instances'] if i['class'] == name],
                'kind': kind, 'declarations': [o['evidence'] for o in occurrences if o['role'] == 'declaration'],
                'writes': writes, 'reads': reads, 'transitions': transitions, 'shadowed_occurrences': shadowed,
                'unit': None, 'unit_status': 'unknown', 'description': None, 'meaning_status': 'unestablished',
                'semantic_evidence': [], 'contradictions': [], 'review_status': 'not_human_reviewed',
                'suitability': 'unresolved', 'limitations': ['Lexical def/use inventory; not reachability or physical-model proof']})
    return {'version': 2, 'model_sha256': sha(model), 'source': str(model),
            'fields': fields, 'inventory_warnings': inventory['warnings'],
            'review_status': 'not_human_reviewed'}


def apply_annotations(model_audit, annotations):
    """Apply analyst claims only with exact citations; no human review inferred."""
    for annotation in annotations:
        if annotation['model_sha256'] != model_audit['model_sha256']:
            continue
        fields = [f for f in model_audit['fields'] if (f['class'], f['variable']) ==
                  (annotation['class'], annotation['variable'])]
        if len(fields) != 1:
            raise ValueError('Annotation does not identify one actual field')
        if not annotation['evidence']:
            raise ValueError('Semantic annotation requires source evidence')
        for item in annotation['evidence']:
            validate_citation(item, model_audit['model_sha256'])
        if annotation['unit_status'] == 'explicit_documentation':
            units = {'metres': r'\bmet(?:re|er)s?\b', 'nautical_miles': r'\bnautical miles?\b'}
            pattern = units.get(annotation['unit'])
            if not pattern or not any(re.search(pattern, e['quote'], re.I) for e in annotation['evidence']):
                raise ValueError('Claimed explicit unit absent from cited documentation')
        if annotation['unit_status'] in ('unknown', 'conflicting') and annotation['unit'] is not None:
            raise ValueError('Unknown/conflicting units cannot be marked known')
        target = fields[0]
        for key in ('description', 'meaning_status', 'unit', 'unit_status', 'suitability', 'contradictions'):
            target[key] = annotation[key]
        target['semantic_evidence'] = annotation['evidence']
        target['annotation_provenance'] = annotation['provenance']
    return model_audit


def build_catalog(models, annotations):
    return {'version': 2, 'models': [apply_annotations(audit(m), annotations) for m in models],
            'mappings': [], 'review_status': 'not_human_reviewed'}


def validate_field(field, model_hash):
    for evidence in field.get('semantic_evidence', []):
        validate_citation(evidence, model_hash)
    for evidence in field.get('declarations', []):
        validate_citation(evidence, model_hash)
    if field.get('unit_status') == 'explicit_documentation' and field.get('unit') is not None:
        pattern = {'metres': r'\bmet(?:re|er)s?\b', 'nautical_miles': r'\bnautical miles?\b'}.get(field['unit'])
        if not pattern or not any(re.search(pattern, e['quote'], re.I) for e in field.get('semantic_evidence', [])):
            raise ValueError('Catalog claims a unit absent from its source citations')
    return (bool(field.get('semantic_evidence')) and field.get('meaning_status') == 'source_supported_scoped'
            and field.get('unit_status') == 'explicit_documentation'
            and not field.get('contradictions') and field.get('suitability') == 'configured_attribute_check')
