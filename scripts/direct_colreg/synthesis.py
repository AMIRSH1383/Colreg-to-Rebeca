import hashlib
import re
from .logic import atoms, effective_applicability, property_text, Unsupported
from .property_io import merge

def renamed(parts, prefix):
    return tuple([re.sub(r'\bG_', prefix, item) for item in group] for group in parts)


def synthesize(data, selected):
    definitions, assertions, witnesses, records = [], [], {}, []
    for requirement in data['formalization']:
        record = {'id': requirement['id'], 'statement_ids': requirement['statement_ids'],
                  'status': 'UNSUPPORTED_SEMANTICS', 'instances': []}
        try:
            if requirement['support'] != 'state' or requirement['temporal'] is not None:
                raise Unsupported(requirement['reason'] or 'Temporal/operational semantics unsupported')
            expressions = [effective_applicability(requirement), requirement['obligation']]
            comparisons = [a for e in expressions for a in atoms(e)]
            keys = {(a['entity'], a['concept']) for a in comparisons}
            if not keys or not keys <= set(selected):
                raise Unsupported('Missing validated model bindings: ' + str(sorted(keys - set(selected))))
            fields = [selected[key] for key in keys]
            if len({key[0] for key in keys}) != 1:
                raise Unsupported('Relations between distinct regulatory entities are not supported')
            if len({f['class'] for f in fields}) != 1:
                raise Unsupported('Cross-class semantics are not supported')
            instances = fields[0]['instances']
            if not instances or any(set(f['instances']) != set(instances) for f in fields):
                raise Unsupported('Bindings must identify the same nonempty actor instance scope')
            pending_definitions, pending_assertions, pending_witnesses = [], [], []
            for instance in instances:
                prefix = 'G_' + requirement['id'] + '_' + instance + '_'
                parts = renamed(property_text(requirement, selected, instance), prefix)
                pending_definitions.extend(parts[0])
                pending_assertions.extend(parts[1])
                witness_parts = property_text(requirement, selected, instance, witness=True)
                # Identical effective antecedents for the same instance share a
                # checker run. Key includes actual rendered field comparisons.
                witness_text = merge('property {}', *witness_parts)
                key = hashlib.sha256(witness_text.encode()).hexdigest()
                pending_witnesses.append((key, witness_text, instance))
            definitions.extend(pending_definitions)
            assertions.extend(pending_assertions)
            for key, witness_text, instance in pending_witnesses:
                witnesses.setdefault(key, {'text': witness_text, 'instance': instance, 'requirements': []})['requirements'].append(requirement['id'])
                record['instances'].append(instance)
            record['status'] = 'GENERATED'
        except (Unsupported, KeyError) as error:
            record['reason'] = str(error)
        records.append(record)
    return definitions, assertions, witnesses, records
