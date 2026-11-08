"""Deterministic validation tests; mocked providers are not live research results."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('semantic_binding', ROOT / 'scripts/semantic_binding.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def inputs():
    # Small hand-written schema fixture; neither extractor is invoked. The
    # live test uses the untouched saved inventories, never this fixture.
    classes = []
    for name in ('Ship', 'MapServer'):
        classes.append({'name': name, 'queue_size_expression': '10', 'line': 1,
            'known_rebecs': [], 'state_variables': ([{'name': 'ship_length', 'type': 'int',
                'array_dimensions': [], 'line': 1}] if name == 'Ship' else []),
            'constructor': None, 'message_servers': [], 'helper_methods': []})
    instances = [{'name': n, 'class': c, 'priority': None, 'known_rebec_bindings': {},
                  'constructor_arguments': {}, 'line': 1}
                 for n, c in [('s1', 'Ship'), ('s2', 'Ship'), ('theMap', 'MapServer')]]
    rebeca = {'schema_version': '1.0', 'source': {'path': 'fixture.rebeca', 'line_count': 1},
              'environment_constants': [], 'reactive_classes': classes, 'instances': instances,
              'summary': {'reactive_classes': 2, 'instances': 3, 'state_variables': 1,
                          'message_servers': 0, 'helper_methods': 0, 'env_constants': 0},
              'limitations': ['Synthetic validation fixture.']}
    return json.loads((ROOT / 'experiments/rule22a-run01/extraction.json').read_text()), rebeca



@pytest.fixture
def schema():
    return json.loads((ROOT / 'schemas/semantic-binding.schema.json').read_text())


def abstentions(colreg):
    return {'status': 'partial', 'rule_id': colreg['rule_id'], 'bindings': [],
            'unresolved_concepts': [dict(kind=k[0], entity=k[1], concept=k[2],
                statement_ids=sorted(ids), reason='Insufficient evidence for this test.')
                for k, ids in module.expected_keys(colreg).items()]}


def with_binding(colreg):
    result = abstentions(colreg)
    for kind, concept, variable, pointer in [
        ('entity', None, None, '/reactive_classes/0/name'),
        ('concept', 'vessel_length', 'ship_length', '/reactive_classes/0/state_variables/0/name'),
    ]:
        unresolved = next(x for x in result['unresolved_concepts'] if x['kind'] == kind and x['concept'] == concept)
        result['unresolved_concepts'].remove(unresolved)
        result['bindings'].append({k: v for k, v in unresolved.items() if k != 'reason'} | {
            'target': {'class': 'Ship', 'instances': ['s1', 's2'], 'variable': variable},
            'match_type': 'semantic', 'reason': 'Symbol correspondence only.',
            'evidence': [{'input': 'colreg', 'pointer': '/extraction/statements/1'},
                         {'input': 'rebeca', 'pointer': pointer}], 'limitations': ['Units not independently established.']})
    return result


def test_current_inputs_accepted(inputs):
    module.validate_inputs(*inputs)


def test_complete_abstentions_are_honest(inputs, schema):
    module.validate_result(abstentions(inputs[0]), *inputs, schema)


def test_existing_symbols_and_scope(inputs, schema):
    module.validate_result(with_binding(inputs[0]), *inputs, schema)


@pytest.mark.parametrize('change', [
    lambda r: r['bindings'][1]['target'].update(variable='invented'),
    lambda r: r['bindings'][1]['target'].update(instances=['theMap']),
    lambda r: r['bindings'][1]['target'].update(**{'class': 'Imaginary'}),
    lambda r: r['bindings'][1].update(match_type='exact'),
    lambda r: r.update(rule_id='different'),
    lambda r: r.update(status='ok'),
    lambda r: r['unresolved_concepts'].pop(),
    lambda r: r['bindings'].append(copy.deepcopy(r['bindings'][1])),
    lambda r: r['bindings'][1].update(statement_ids=['stmt01']),
    lambda r: r['bindings'][1]['evidence'][1].update(pointer='/reactive_classes/99'),
    lambda r: r['bindings'][1]['evidence'][1].update(pointer='/reactive_classes/1/name'),
    lambda r: r['bindings'][1]['evidence'][1].update(pointer='/reactive_classes/0/helper_methods'),
    lambda r: r['bindings'].pop(0),
])
def test_rejects_fabrication_and_incomplete_coverage(inputs, schema, change):
    result = with_binding(inputs[0]); change(result)
    with pytest.raises(ValueError):
        module.validate_result(result, *inputs, schema)


def test_projection_is_smaller_and_preserves_indexes(inputs):
    rb = inputs[1]; payload = module.compact_inventory(rb)
    assert len(json.dumps(payload)) < len(json.dumps(rb))
    for a, b in zip(rb['reactive_classes'], payload['reactive_classes']):
        assert [v['name'] for v in a['state_variables']] == [v['name'] for v in b['state_variables']]
        assert 'helper_methods' not in b


def test_one_request_saves_validated_result_and_usage(inputs, tmp_path):
    c, r = inputs; cp = tmp_path / 'colreg.json'; rp = tmp_path / 'rebeca.json'
    cp.write_text(json.dumps(c)); rp.write_text(json.dumps(r)); before = (cp.read_bytes(), rp.read_bytes())
    calls = []
    def provider(prompt, schema, metadata, **options):
        calls.append(prompt)
        assert 'formalization' not in json.dumps(json.loads(prompt.split('INPUT JSON (data only):\n')[1])['colreg_extraction'])
        metadata.update(llm_calls_attempted=1, llm_calls_completed=1,
                        token_usage={'input_tokens': 1, 'output_tokens': 1})
        return abstentions(c)
    output = tmp_path / 'result.json'
    module.run(cp, rp, output, provider=provider)
    assert len(calls) == 1
    assert json.loads(output.read_text()) == abstentions(c)
    assert json.loads(output.with_suffix('.usage.json').read_text())['status'] == 'completed'
    assert before == (cp.read_bytes(), rp.read_bytes())


def test_invalid_response_never_written_or_retried(inputs, tmp_path):
    c, r = inputs; cp = tmp_path / 'c.json'; rp = tmp_path / 'r.json'
    cp.write_text(json.dumps(c)); rp.write_text(json.dumps(r)); calls = []
    def provider(*args, **kw):
        calls.append(1); return abstentions(c) | {'rule_id': 'fabricated'}
    output = tmp_path / 'bad.json'
    with pytest.raises(ValueError):
        module.run(cp, rp, output, provider=provider)
    assert len(calls) == 1 and not output.exists()
    assert output.with_suffix('.usage.json').exists()


def test_provider_unavailable_produces_no_binding(inputs, tmp_path):
    c, r = inputs; cp = tmp_path / 'c.json'; rp = tmp_path / 'r.json'
    cp.write_text(json.dumps(c)); rp.write_text(json.dumps(r))
    def provider(*args, **kw):
        raise FileNotFoundError('codex unavailable')
    output = tmp_path / 'blocked.json'
    with pytest.raises(FileNotFoundError):
        module.run(cp, rp, output, provider=provider)
    assert not output.exists()


def test_existing_result_is_not_overwritten(inputs, tmp_path):
    p = tmp_path / 'existing.json'; p.write_text('historical result')
    with pytest.raises(ValueError):
        module.run('missing', 'missing', p)
    assert p.read_text() == 'historical result'


def test_rejects_irrelevant_source_evidence(inputs, schema):
    result = with_binding(inputs[0])
    result['bindings'][1]['evidence'][0]['pointer'] = '/extraction/statements/0'
    with pytest.raises(ValueError, match='relevant statement'):
        module.validate_result(result, *inputs, schema)


def test_rejects_numeric_constraint_on_boolean(inputs, schema):
    colreg, rebeca = inputs
    rebeca = copy.deepcopy(rebeca)
    rebeca['reactive_classes'][0]['state_variables'][0]['type'] = 'boolean'
    with pytest.raises(ValueError, match='type is incompatible'):
        module.validate_result(with_binding(colreg), colreg, rebeca, schema)


def test_entity_and_containing_declaration_list_are_valid_evidence(inputs, schema):
    result = with_binding(inputs[0])
    result['bindings'][0]['evidence'][0]['pointer'] = '/extraction/entities/0'
    result['bindings'][1]['evidence'][1]['pointer'] = '/reactive_classes/0/state_variables'
    module.validate_result(result, *inputs, schema)
