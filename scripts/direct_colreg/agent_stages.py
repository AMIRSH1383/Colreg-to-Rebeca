"""Explicit binding-to-synthesis handoff; all outputs remain in isolated folders."""
import hashlib
import json
from pathlib import Path
import shutil
from .binding import bind
from .synthesis import synthesize
from .property_io import merge


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def handoff(data, selected, records, model_path, extraction_path=None):
    return {'version': 1, 'rule_id': data['rule_id'], 'model_sha256': digest(model_path),
            'extraction_sha256': digest(extraction_path) if extraction_path else None,
            'semantic_review': 'REQUIRES_INDEPENDENT_REVIEW',
            'bindings': [{'entity': entity, 'concept': concept, 'field': field}
                         for (entity, concept), field in selected.items()],
            'records': records}


def validate_handoff(artifact, inventory, model_path, extraction_path):
    if artifact.get('version') != 1 or artifact['model_sha256'] != digest(model_path):
        raise ValueError('Binding handoff does not match the exact input model')
    if artifact['extraction_sha256'] != digest(extraction_path):
        raise ValueError('Binding handoff does not match the exact extraction')
    actual = {(a['name'], v['name']): v['type'] for a in inventory['reactive_classes']
              for v in a['state_variables']}
    owners = {i['name']: i['class'] for i in inventory['instances']}
    selected = {}
    for entry in artifact['bindings']:
        field = entry['field']
        key = (entry['entity'], entry['concept'])
        if key in selected or actual.get((field['class'], field['variable'])) != field['type']:
            raise ValueError('Duplicate binding or nonexistent/incompatible model field')
        if not field['instances'] or any(owners.get(i) != field['class'] for i in field['instances']):
            raise ValueError('Binding actor scope does not match the actual model')
        selected[key] = field
    return selected


def write_synthesis(data, selected, model_path, output, property_path=None):
    output = Path(output)
    # Public function can be called outside the fresh-directory CLI. Refuse
    # existing artifacts before writing anything, including the source itself.
    targets = [output / 'model.rebeca', output / 'model.property', output / 'synthesis.json']
    if any(p.exists() for p in targets) or list(output.glob('applicability-*.property')):
        raise ValueError('Synthesis output already contains artifacts; use a fresh directory')
    output.mkdir(parents=True, exist_ok=True)
    definitions, assertions, witnesses, records = synthesize(data, selected)
    manifest = {'status': 'GENERATED_SUPPORTED_SUBSET' if assertions else 'UNSUPPORTED_SEMANTICS',
                'requirements': records, 'model_sha256': digest(model_path),
                'model_changes': [], 'verification': 'NOT_RUN', 'full_source_verified': False,
                'generated_property': None, 'applicability_properties': []}
    if assertions:
        original = Path(property_path).read_text(encoding='utf-8-sig') if property_path else 'property {}'
        rendered = merge(original, definitions, assertions)
        shutil.copyfile(model_path, output / 'model.rebeca')
        (output / 'model.property').write_text(rendered, encoding='utf-8', newline='')
        manifest.update(model_preserved=digest(output / 'model.rebeca') == digest(model_path),
                        generated_property=str(output / 'model.property'),
                        generated_property_sha256=digest(output / 'model.property'),
                        original_property_sha256=digest(property_path) if property_path else None)
        for i, witness in enumerate(witnesses.values()):
            path = output / f'applicability-{i}.property'
            path.write_text(witness['text'], encoding='utf-8')
            manifest['applicability_properties'].append({'path': str(path),
                'requirements': witness['requirements'], 'instance': witness['instance']})
    (output / 'synthesis.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest
