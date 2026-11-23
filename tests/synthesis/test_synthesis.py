"""Synthetic unit fixtures are not recovered Rule 22(a) binding artifacts."""
import copy
import json
from pathlib import Path

import pytest

from scripts.synthesis.synthesis import ROOT, main, prepare, validate_response
from scripts.synthesis.apply_model_patches import apply_patches, digest
from tests.fixtures import RULE22A_HANDOFF, rule22a_synthesis_response

SOURCE = b'''reactiveclass Ship(5) {
statevars { int length; int range; }
Ship(int l) { length = l; range = 2; }
msgsrv tick() { self.tick() after(1); }
}
main { Ship s1():(12); Ship s2():(10); }
'''


def fixture():
    colreg = {'status': 'ok', 'rule_id': 'Test', 'extraction': {
        'entities': [{'id': 'vessel', 'name': 'vessel', 'type': 'participant', 'source_text': 'vessel'}],
        'statements': [], 'references': []}, 'open_assumptions': []}
    for sid, role, concept, value, deps in [('stmt01', 'scope', 'length', 50, []), ('stmt02', 'obligation', 'range', 6, ['stmt01'])]:
        colreg['extraction']['statements'].append({'id': sid, 'role': role, 'source_text': 'test source', 'subjects': ['vessel'], 'concept': concept, 'predicate': 'test comparison', 'operator': '>=', 'value': value, 'unit': None, 'applies_when': deps})
    bindings = []
    for concept, ids in [(None, ['stmt01', 'stmt02']), ('length', ['stmt01']), ('range', ['stmt02'])]:
        bindings.append({'kind': 'entity' if concept is None else 'concept', 'entity': 'vessel', 'concept': concept, 'statement_ids': ids,
                         'target': {'class': 'Ship', 'instances': ['s1', 's2'], 'variable': concept}, 'match_type': 'exact', 'reason': 'Synthetic established dimensionless test mapping',
                         'evidence': [{'input': 'colreg', 'pointer': '/extraction/entities/0'}, {'input': 'rebeca', 'pointer': '/reactive_classes/0'}], 'limitations': []})
    return colreg, {'status': 'ok', 'rule_id': 'Test', 'bindings': bindings, 'unresolved_concepts': []}


def response(request):
    return {'property_content': request['canonical_supported_property'], 'patches': [],
            'requirements': [{'statement_id': s['id'], 'disposition': 'unresolved' if s['id'] in request['blocked'] else ('context' if s['role'] == 'scope' else 'generated'), 'reason': 'Synthetic test disposition'} for s in request['colreg']['extraction']['statements']],
            'unresolved': ['Synthetic unresolved summary'] if request['blocked'] or request['semantic_uncertainties'] else []}


def test_supported_scoped_property_and_actors():
    request, model = prepare(*fixture(), SOURCE)
    result = response(request)
    validate_response(result, request, model)
    assert result['property_content'] == ('property {\n  Assertion {\n'
        '    stmt02_vessel_s1: !((s1.length >= 50)) || (s1.range >= 6);\n'
        '    stmt02_vessel_s2: !((s2.length >= 50)) || (s2.range >= 6);\n  }\n}\n')
    assert 'self.tick' not in json.dumps(request)


@pytest.fixture
def rule22a_inputs():
    colreg = json.loads((RULE22A_HANDOFF / 'colreg_extraction.json').read_text())
    binding = json.loads((RULE22A_HANDOFF / 'semantic_binding.json').read_text())
    return colreg, binding, (ROOT / 'inputs/rebeca/original_model.rebeca').read_bytes()


def test_prescribed_light_assumption_preserves_ten_scoped_checks(rule22a_inputs):
    request, model = prepare(*rule22a_inputs)
    result = rule22a_synthesis_response(request)
    assumed = request['assumed_prerequisites']
    assert set(request['blocked']) == {'stmt01', 'stmt02'}
    assert assumed == {f'stmt{i:02}': 'stmt01' for i in range(4, 9)}
    assert validate_response(result, request, model) == set(assumed)
    note = ('These symbolic range checks assume the checked lights are prescribed for the vessel. '
            'Legal applicability remains unresolved.')
    text = result['property_content']
    assert '// ' + note in text
    assertions = [line.strip() for line in text.splitlines() if line.startswith('    ')]
    ranges = (('masthead_light_range', 6), ('side_light_range', 3), ('stern_light_range', 3),
              ('towing_light_range', 3), ('allround_light_range', 3))
    assert assertions == [
        f'stmt{i:02}_vessel_{actor}: !(({actor}.ship_length >= 50)) || ({actor}.{field} >= {threshold});'
        for i, (field, threshold) in enumerate(ranges, start=4) for actor in ('s1', 's2')
    ]
    result['unresolved'].remove(note)
    with pytest.raises(ValueError, match='Missing prescribed-light applicability assumption'):
        validate_response(result, request, model)


@pytest.mark.parametrize('case', ['different_rule', 'unknown_qualifier', 'missing_length', 'nested_qualifier'])
def test_prescribed_light_exception_cannot_erase_other_guards(rule22a_inputs, case):
    colreg, binding, source = rule22a_inputs
    qualifier, _, length, *ranges = colreg['extraction']['statements']
    if case == 'different_rule':
        colreg['rule_id'] = binding['rule_id'] = 'OtherRule'
    elif case == 'unknown_qualifier':
        qualifier['source_text'] = 'A different unmodeled condition'
    elif case == 'nested_qualifier':
        qualifier['applies_when'] = [length['id']]
    else:
        for statement in ranges:
            statement['applies_when'].remove(length['id'])
    request, _ = prepare(colreg, binding, source)
    assert not request['assumed_prerequisites']
    assert not request['eligible_statements']
    assert all('Unresolved prerequisite stmt01' in request['blocked'][s['id']] for s in ranges)
    assert request['canonical_supported_property'] == ''


@pytest.mark.parametrize('mutation', ['threshold', 'actor', 'scope', 'tautology'])
def test_rejects_invented_property(mutation):
    request, model = prepare(*fixture(), SOURCE)
    result = response(request)
    before, after = {'threshold': ('>= 6', '>= 3'), 'actor': ('s2.range', 's3.range'), 'scope': ('>= 50', '> 50'), 'tautology': ('(s1.range >= 6)', 'true')}[mutation]
    result['property_content'] = result['property_content'].replace(before, after)
    with pytest.raises(ValueError, match='Property differs'):
        validate_response(result, request, model)


@pytest.mark.parametrize('uncertainty', ['unit', 'limitation', 'assumption'])
def test_uncertainty_is_reported_without_vetoing_symbolic_candidates(uncertainty):
    colreg, binding = fixture()
    if uncertainty == 'unit':
        colreg['extraction']['statements'][0]['unit'] = 'metres'
    elif uncertainty == 'limitation':
        binding['bindings'][1]['limitations'] = ['Unknown semantics']
    else:
        colreg['open_assumptions'] = [{'source_text': 'test', 'reason': 'unknown'}]
    request, model = prepare(colreg, binding, SOURCE)
    assert request['blocked'] == {}
    assert request['eligible_statements'] == ['stmt02']
    assert 'stmt02' in request['semantic_uncertainties']
    assert 'CONDITIONAL SYMBOLIC CHECKS' in request['canonical_supported_property']
    assert '!((s1.length >= 50)) || (s1.range >= 6)' in request['canonical_supported_property']
    validate_response(response(request), request, model)


@pytest.mark.parametrize('fault', ['field', 'instance', 'coverage', 'evidence', 'cycle', 'partial_actors', 'duplicate'])
def test_invalid_inputs(fault):
    colreg, binding = fixture()
    if fault == 'field':
        binding['bindings'][1]['target']['variable'] = 'invented'
    elif fault == 'instance':
        binding['bindings'][1]['target']['instances'] = ['s3']
    elif fault == 'coverage':
        binding['bindings'].pop()
    elif fault == 'evidence':
        binding['bindings'][1]['evidence'][0]['pointer'] = '/missing'
    elif fault == 'cycle':
        colreg['extraction']['statements'][0]['applies_when'] = ['stmt01']
    elif fault == 'partial_actors':
        binding['bindings'][1]['target']['instances'] = ['s1']
    else:
        binding['bindings'].append(copy.deepcopy(binding['bindings'][1]))
    with pytest.raises(ValueError):
        prepare(colreg, binding, SOURCE)


def test_pure_observer_patch_and_reject_behavior():
    request, model = prepare(*fixture(), SOURCE)
    result = response(request)
    section = request['sections'][0]
    patch = {'section_id': section['id'], 'section_sha256': section['sha256'], 'old': '}',
             'new': 'boolean observed() { return range >= 6; }\n}', 'reason': 'Test observation'}
    result['patches'] = [patch]
    validate_response(result, request, model)
    changed = apply_patches(SOURCE, digest(SOURCE), request['sections'], result['patches'])
    assert b'length = l; range = 2;' in changed
    patch['new'] = 'msgsrv cheat() { range = 6; }\n}'
    with pytest.raises(ValueError, match='pure observation'):
        validate_response(result, request, model)


def test_missing_disposition():
    request, model = prepare(*fixture(), SOURCE)
    result = response(request)
    result['requirements'].pop()
    with pytest.raises(ValueError, match='Incomplete'):
        validate_response(result, request, model)


def test_cli_external_response_and_preservation(tmp_path):
    colreg, binding = fixture()
    request, _ = prepare(colreg, binding, SOURCE)
    for name, value in [('colreg', colreg), ('binding', binding), ('response', response(request))]:
        (tmp_path / (name + '.json')).write_text(json.dumps(value))
    (tmp_path / 'model.rebeca').write_bytes(SOURCE)
    out = tmp_path / 'result'
    args = ['--colreg', str(tmp_path / 'colreg.json'), '--binding', str(tmp_path / 'binding.json'), '--model', str(tmp_path / 'model.rebeca'), '--response', str(tmp_path / 'response.json'), '--output-dir', str(out)]
    assert main(args) == 0
    assert (out / 'model.rebeca').read_bytes() == SOURCE
    assert (out / 'model.diff').read_bytes() == b''
    assert (out / 'model.property').read_text() == response(request)['property_content']
    assert main(args) == 1
    assert (tmp_path / 'model.rebeca').read_bytes() == SOURCE


def test_missing_binding_fails_before_provider_or_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr('scripts.synthesis.synthesis.invoke_codex', lambda *a: pytest.fail('Provider must not run'))
    output = tmp_path / 'result'
    assert main(['--colreg', str(RULE22A_HANDOFF / 'colreg_extraction.json'), '--binding', str(tmp_path / 'missing.json'), '--model', str(ROOT / 'inputs/rebeca/original_model.rebeca'), '--output-dir', str(output), '--prepare-only']) == 1
    assert not output.exists()


@pytest.mark.parametrize('expression', ['range > 6', 'range >= -6', 'range >= 7', 'range >= 6 >= 6', 'range++', 'unknown >= 6', 'tick()', 'true'])
def test_rejects_unsupported_observer(expression):
    request, model = prepare(*fixture(), SOURCE)
    result = response(request)
    section = request['sections'][0]
    result['patches'] = [{'section_id': section['id'], 'section_sha256': section['sha256'], 'old': '}', 'new': f'boolean observe() {{ return {expression}; }}\n}}', 'reason': 'test'}]
    with pytest.raises(ValueError):
        validate_response(result, request, model)


def test_fully_blocked_run_has_no_property_file(tmp_path):
    colreg, binding = fixture()
    colreg['extraction']['statements'][1]['operator'] = None
    request, _ = prepare(colreg, binding, SOURCE)
    for name, value in [('colreg', colreg), ('binding', binding), ('response', response(request))]:
        (tmp_path / (name + '.json')).write_text(json.dumps(value))
    (tmp_path / 'model.rebeca').write_bytes(SOURCE)
    out = tmp_path / 'result'
    assert main(['--colreg', str(tmp_path / 'colreg.json'), '--binding', str(tmp_path / 'binding.json'), '--model', str(tmp_path / 'model.rebeca'), '--response', str(tmp_path / 'response.json'), '--output-dir', str(out)]) == 0
    assert not (out / 'model.property').exists()
    assert (out / 'model.rebeca').read_bytes() == SOURCE
    assert json.loads((out / 'report.json').read_text())['status'] == 'partial'


def test_provider_one_turn_usage_and_compact_input(monkeypatch):
    from types import SimpleNamespace
    from scripts.synthesis.synthesis import invoke_codex
    request, _ = prepare(*fixture(), SOURCE)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert 'self.tick' not in kwargs['input']
        assert kwargs['timeout'] == 10
        assert '--ephemeral' in command
        assert 'features.shell_tool=false' in command
        assert not list(Path(command[command.index('-C') + 1]).iterdir())
        Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(response(request)))
        return SimpleNamespace(returncode=0, stdout=json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 100, 'output_tokens': 50}}))
    monkeypatch.setattr('scripts.synthesis.synthesis.subprocess.run', run)
    result, usage = invoke_codex(request, 10)
    assert len(calls) == 1
    assert usage['invocations'] == 1
    assert usage['input_tokens'] == 100
    assert usage['output_tokens'] == 50
    assert result == response(request)


@pytest.mark.parametrize('tool_type', ['command_execution', 'mcp_tool_call', 'custom_tool_call', 'collab_tool_call'])
def test_provider_tool_output_rejected(monkeypatch, tool_type):
    from types import SimpleNamespace
    from scripts.synthesis.synthesis import invoke_codex
    monkeypatch.setattr('scripts.synthesis.synthesis.subprocess.run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps({'type': 'item.completed', 'item': {'type': tool_type}})))
    request, _ = prepare(*fixture(), SOURCE)
    with pytest.raises(ValueError, match='used tools'):
        invoke_codex(request, 10)


def test_portable_agent_copy_matches():
    assert (ROOT / 'agents/synthesis_agent.md').read_bytes() == (ROOT / '.opencode/agents/synthesis_agent.md').read_bytes()


def test_unmapped_intensity_does_not_block_scoped_ranges():
    colreg, binding = fixture()
    intensity = dict(colreg['extraction']['statements'][1], id='stmt03', concept='intensity', operator=None, value=None, applies_when=[])
    colreg['extraction']['statements'].append(intensity)
    binding['bindings'][0]['statement_ids'].append('stmt03')
    binding['status'] = 'partial'
    binding['unresolved_concepts'] = [{'kind': 'concept', 'entity': 'vessel', 'concept': 'intensity', 'statement_ids': ['stmt03'], 'reason': 'No model field or Annex I definition'}]
    binding['bindings'][0]['limitations'] = ['Participant correspondence does not establish compliance.']
    colreg['extraction']['statements'][0]['unit'] = 'metres'
    colreg['extraction']['statements'][1]['unit'] = 'miles'
    request, model = prepare(colreg, binding, SOURCE)
    assert set(request['blocked']) == {'stmt03'}
    assert request['eligible_statements'] == ['stmt02']
    assert 'stmt01' in request['semantic_uncertainties']
    assert 's1.length >= 50' in request['canonical_supported_property']
    assert 's2.range >= 6' in request['canonical_supported_property']
    assert 'intensity' not in request['canonical_supported_property']
    validate_response(response(request), request, model)


def test_missing_scope_blocks_dependents_but_not_independent_obligation():
    colreg, binding = fixture()
    colreg['extraction']['statements'][0]['operator'] = None
    independent = dict(colreg['extraction']['statements'][1], id='stmt03', applies_when=[])
    colreg['extraction']['statements'].append(independent)
    binding['bindings'][0]['statement_ids'].append('stmt03')
    binding['bindings'][2]['statement_ids'].append('stmt03')
    request, model = prepare(colreg, binding, SOURCE)
    assert set(request['blocked']) == {'stmt01', 'stmt02'}
    assert request['eligible_statements'] == ['stmt03']
    validate_response(response(request), request, model)


def test_generated_obligation_cannot_claim_its_guard_unresolved():
    request, model = prepare(*fixture(), SOURCE)
    result = response(request)
    result['requirements'][0]['disposition'] = 'unresolved'
    with pytest.raises(ValueError, match='guard'):
        validate_response(result, request, model)


@pytest.mark.parametrize('outcome', ['nonzero', 'timeout', 'launch_failed', 'missing_response'])
def test_cli_diagnostics_survive_failure(monkeypatch, tmp_path, outcome):
    import subprocess
    from types import SimpleNamespace
    from scripts.synthesis.synthesis import invoke_codex
    request, _ = prepare(*fixture(), SOURCE)
    def run(*args, **kwargs):
        if outcome == 'timeout':
            raise subprocess.TimeoutExpired('codex', 5, output=b'partial stdout', stderr=b'partial stderr')
        if outcome == 'launch_failed':
            raise FileNotFoundError('codex not found')
        return SimpleNamespace(returncode=1 if outcome == 'nonzero' else 0, stderr='underlying diagnostic', stdout=json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 42, 'output_tokens': 7}}))
    monkeypatch.setattr('scripts.synthesis.synthesis.subprocess.run', run)
    with pytest.raises((RuntimeError, OSError, subprocess.TimeoutExpired)) as error:
        invoke_codex(request, 5, tmp_path)
    assert (tmp_path / 'cli.stdout.jsonl').exists()
    stderr = (tmp_path / 'cli.stderr.log').read_text()
    if outcome in ('nonzero', 'missing_response'):
        assert 'underlying diagnostic' in str(error.value)
        assert stderr == 'underlying diagnostic'
        assert json.loads((tmp_path / 'usage.result.json').read_text())['input_tokens'] == 42
    if outcome == 'timeout':
        assert stderr == 'partial stderr'
    assert (tmp_path / 'cli.diagnostics.json').exists()


@pytest.mark.parametrize('outcome', ['success', 'timeout'])
def test_cli_uses_private_writable_state_and_preserves_parent(monkeypatch, tmp_path, outcome):
    import os
    import stat
    import subprocess
    from types import SimpleNamespace
    from scripts.synthesis.synthesis import invoke_codex
    source_home = tmp_path / 'readonly-source'
    source_home.mkdir()
    originals = {'auth.json': '{"test_credential":"synthetic"}', 'config.toml': '# test config\n'}
    for name, content in originals.items():
        (source_home / name).write_text(content)
        (source_home / name).chmod(0o400)
    monkeypatch.setenv('CODEX_HOME', str(source_home))
    monkeypatch.setenv('HTTPS_PROXY', 'http://synthetic-proxy.invalid')
    parent_home = os.environ.get('HOME')
    seen = []
    request, _ = prepare(*fixture(), SOURCE)
    def run(command, **kwargs):
        child = kwargs['env']
        state = Path(child['CODEX_HOME'])
        seen.append(state)
        assert state != source_home
        assert stat.S_IMODE(state.stat().st_mode) == 0o700
        assert child.get('HOME') == parent_home
        assert child['HTTPS_PROXY'] == os.environ['HTTPS_PROXY']
        assert os.environ['CODEX_HOME'] == str(source_home)
        assert not list(Path(command[command.index('-C') + 1]).iterdir())
        for name, content in originals.items():
            assert (state / name).read_text() == content
            assert stat.S_IMODE((state / name).stat().st_mode) == 0o600
        (state / 'installation_id').write_text('writable')
        if outcome == 'timeout':
            raise subprocess.TimeoutExpired('codex', 5)
        Path(command[command.index('--output-last-message') + 1]).write_text(json.dumps(response(request)))
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr('scripts.synthesis.synthesis.subprocess.run', run)
    if outcome == 'timeout':
        with pytest.raises(subprocess.TimeoutExpired):
            invoke_codex(request, 5)
    else:
        invoke_codex(request, 5)
    assert len(seen) == 1 and not seen[0].exists()
    for name, content in originals.items():
        assert (source_home / name).read_text() == content
        assert stat.S_IMODE((source_home / name).stat().st_mode) == 0o400
    assert not (source_home / 'installation_id').exists()


def test_prepare_and_import_never_call_provider(monkeypatch, tmp_path):
    from scripts.extraction.rebeca_extractor import parse_model
    monkeypatch.setattr('scripts.synthesis.synthesis.invoke_codex', lambda *a: pytest.fail('No nested CLI'))
    monkeypatch.setattr('scripts.synthesis.synthesis.subprocess.run', lambda *a, **kw: pytest.fail('No child processes'))
    colreg, binding = fixture()
    for name, value in [('colreg', colreg), ('binding', binding), ('rebeca', parse_model(SOURCE.decode(), '<input>'))]:
        (tmp_path / (name + '.json')).write_text(json.dumps(value))
    model_path = tmp_path / 'model.rebeca'
    model_path.write_bytes(SOURCE)
    base = ['--colreg', str(tmp_path / 'colreg.json'), '--binding', str(tmp_path / 'binding.json'), '--rebeca', str(tmp_path / 'rebeca.json'), '--model', str(model_path)]
    prepared, final = tmp_path / 'prepared', tmp_path / 'final'
    assert main(base + ['--output-dir', str(prepared), '--prepare-only']) == 0
    request = json.loads((prepared / 'request.json').read_text())
    assert len(request['input_provenance']) == 4
    assert not (prepared / 'model.property').exists()
    response_path = tmp_path / 'hosted-response.json'
    response_path.write_text(json.dumps(response(request)))
    assert main(base + ['--output-dir', str(final), '--response', str(response_path)]) == 0
    assert json.loads((final / 'request.json').read_text()) == request
    assert (final / 'model.rebeca').read_bytes() == SOURCE
    assert json.loads((final / 'usage.json').read_text())['invocations'] == 0
    assert (final / 'model.property').read_text() == response(request)['property_content']
    assert json.loads(response_path.read_text()) == json.loads((final / 'response.json').read_text())
    # Tamper with a saved upstream inventory: fail before producing artifacts.
    saved = json.loads((tmp_path / 'rebeca.json').read_text())
    saved['reactive_classes'][0]['state_variables'][0]['name'] = 'stale_name'
    (tmp_path / 'rebeca.json').write_text(json.dumps(saved))
    stale_out = tmp_path / 'stale'
    assert main(base + ['--output-dir', str(stale_out), '--prepare-only']) == 1
    assert not stale_out.exists()


def test_synthesis_requires_explicit_prepare_or_import(monkeypatch, tmp_path):
    monkeypatch.setattr('scripts.synthesis.synthesis.invoke_codex', lambda *a: pytest.fail('No implicit CLI'))
    with pytest.raises(SystemExit) as exc:
        main(['--colreg', 'missing.json', '--binding', 'missing.json', '--model', 'missing.rebeca', '--output-dir', str(tmp_path / 'out')])
    assert exc.value.code == 2
