"""Coordinator handoffs using saved specialist responses and an isolated RMC stub."""
import json
from pathlib import Path

import pytest

from scripts.coordinator import pipeline
from scripts.utilities.experiment_store import ROOT, Experiment

SAVED = ROOT / 'experiments/Rule22a'


def invoke(capsys, *args):
    code = pipeline.main(['--rule-id', 'Rule22a', *map(str, args)])
    captured = capsys.readouterr()
    return code, json.loads(captured.out)


def resume(capsys, common, checkpoint, response, *extra):
    return invoke(capsys, *common, '--resume', checkpoint['request_id'],
                  '--response', response, *extra)


def test_discovery():
    rule, agent_id, colreg, model = pipeline.rule_inputs('Rule-22a', None, None)
    assert (rule, agent_id, colreg) == ('Rule22a', 'Rule-22a', ROOT / 'inputs/colreg/Rule22_baseline_colreg.txt')
    assert model == ROOT / 'inputs/rebeca/original_model.rebeca'
    assert pipeline.rule_inputs('Rule19ab', None, None)[:2] == ('Rule19ab', 'Rule-19')
    with pytest.raises(ValueError, match='Supply --colreg'):
        pipeline.rule_inputs('Rule999', None, None)


@pytest.fixture
def run_setup(tmp_path, monkeypatch):
    from scripts.binding import semantic_binding
    from scripts.synthesis import synthesis

    def forbidden(*args, **kwargs):
        pytest.fail('Coordinator attempted nested inference')

    monkeypatch.setattr(semantic_binding, 'call_codex', forbidden)
    monkeypatch.setattr(synthesis, 'invoke_codex', forbidden)
    jar = tmp_path / 'timing.jar'
    jar.write_bytes(b'stub')
    config = tmp_path / 'rmc.json'
    config.write_text(json.dumps({'jar': str(jar), 'sha256': pipeline.digest(jar)}))
    monkeypatch.setattr(pipeline, 'RMC_CONFIG', config)
    exp = Experiment('Rule22a', tmp_path / 'experiments')
    calls = []
    outcome = {'gate': 'satisfied', 'xml': 'satisfied'}

    def gate(**kwargs):
        calls.append(kwargs)
        result = pipeline.read(SAVED / 'verification/result.json')
        status = outcome['gate']
        result.update(verified=status == 'satisfied', passes_gate=status == 'satisfied',
                      verification_status=status, verification_outcome=status)
        folder = Path(kwargs['output_dir']) / 'rmc'
        folder.mkdir(parents=True)
        xml = folder / 'model_result.xml'
        xml.write_text(f'<model-checking-report><checked-property><result>{outcome["xml"]}'
                       '</result></checked-property></model-checking-report>')
        (folder / 'rmc_stderr.log').write_text('fixture diagnostic')
        result['rmc_details']['output_dir'] = str(folder)
        result['rmc_details']['result_artifact']['path'] = str(xml)
        if status == 'execution_failed':
            result['rmc_details']['model_out']['error'] = 'fixture timeout'
        return result

    monkeypatch.setattr(pipeline.verify_gate, 'run_verification_gate', gate)
    return ['--experiments-dir', str(exp.folder.parent)], exp, calls, outcome, jar


def to_synthesis(capsys, common):
    code, first = invoke(capsys, *common)
    assert code == 0 and first['stage'] == 'colreg_extraction'
    request = pipeline.read(first['request'])
    assert request['agent'] == 'colreg_extractor'
    assert Path(request['instructions']) == ROOT / 'agents/colreg_extractor.md'
    assert Path(request['input']['colreg_input']).name == 'Rule22_baseline_colreg.txt'
    code, second = resume(capsys, common, first, SAVED / 'colreg_extraction.json')
    assert code == 0 and second['stage'] == 'binding'
    request = pipeline.read(second['request'])
    assert request['agent'] == 'semantic_binding_agent'
    assert Path(request['schema']).name == 'semantic-binding.schema.json'
    assert 'message_servers' not in request['input']['rebeca_extraction']['reactive_classes'][0]
    code, third = resume(capsys, common, second, SAVED / 'semantic_binding.json')
    assert code == 0 and third['stage'] == 'synthesis'
    request = pipeline.read(third['request'])
    assert request['agent'] == 'synthesis_agent'
    assert Path(request['schema']).name == 'synthesis.schema.json'
    assert request['input']['source_sha256'] == pipeline.digest(ROOT / 'inputs/rebeca/original_model.rebeca')
    return third


def test_order_full_rerun_reuse_and_failed_verification(capsys, run_setup):
    common, exp, calls, outcome, jar = run_setup
    full = [*common, '--full-rerun']
    third = to_synthesis(capsys, full)
    assert not calls
    code, result = resume(capsys, full, third, SAVED / 'synthesis/response.json', '--input-tokens', '10')
    assert code == 0 and result['status'] == 'completed'
    report = pipeline.read(result['report'])
    assert all(v['status'] == 'executed' for v in report['stages'].values())
    assert report['binding_status'] == report['synthesis_status'] == 'partial'
    assert report['llm']['passes_reported_this_invocation'] == 3
    assert report['llm']['input_tokens'] is None  # two calls did not supply counts
    assert report['incomplete_checks'] == ['vacuity', 'mutation']
    assert calls[0]['jar'] == str(jar)
    assert Path(calls[0]['model']) == exp.folder / 'synthesis/model.rebeca'
    assert Path(calls[0]['property_file']) == exp.folder / 'synthesis/model.property'
    assert report['verification']['outcome'] == 'satisfied'
    assert report['regulatory_compliance'] == 'not_established'
    assert exp.folder.joinpath('synthesis/model.property').read_bytes() == (SAVED / 'synthesis/model.property').read_bytes()

    code, result = invoke(capsys, *common, '--reuse')
    report = pipeline.read(result['report'])
    assert code == 0 and all(report['stages'][s]['status'] == 'reused' for s in pipeline.STAGES)
    assert report['llm']['passes_reported_this_invocation'] == 0
    assert len(calls) == 1

    previous = (exp.folder / 'verification/result.json').read_bytes()
    outcome.update(gate='execution_failed', xml='unknown')
    third = to_synthesis(capsys, full)
    code, result = resume(capsys, full, third, SAVED / 'synthesis/response.json')
    assert code == 1 and result['error']['stage'] == 'verification'
    report = pipeline.read(result['report'])
    assert report['verification']['outcome'] == 'execution_failed'
    assert report['verification']['error'] == 'fixture timeout'
    assert (exp.folder / 'verification/result.json').read_bytes() == previous
    assert exp.inspect()['stages']['verification']['last_attempt']['status'] == 'failed'


def test_stale_source_blocks_resume_then_rejects_stale_reuse(capsys, run_setup, tmp_path):
    common, exp, _, _, _ = run_setup
    source = tmp_path / 'rule.txt'
    source.write_bytes((ROOT / 'inputs/colreg/Rule22_baseline_colreg.txt').read_bytes())
    common += ['--colreg', str(source)]
    _, pending = invoke(capsys, *common)
    source.write_bytes(source.read_bytes() + b'\n')
    code, result = resume(capsys, common, pending, SAVED / 'colreg_extraction.json')
    assert code == 1 and result['error']['stage'] == 'colreg_extraction'
    assert 'changed' in result['error']['message']
    assert not (exp.folder / 'colreg_extraction.json').exists()

    _, pending = invoke(capsys, *common)
    _, binding = resume(capsys, common, pending, SAVED / 'colreg_extraction.json')
    source.write_bytes(source.read_bytes() + b'\n')
    code, result = resume(capsys, common, binding, SAVED / 'semantic_binding.json')
    assert code == 1 and 'colreg_extraction changed' in result['error']['message']
    _, pending = invoke(capsys, *common)
    assert pending['stage'] == 'colreg_extraction'


def test_valid_partial_without_property_skips_verification(capsys, run_setup):
    common, exp, calls, _, _ = run_setup
    checkpoint = to_synthesis(capsys, common)
    response = pipeline.read(SAVED / 'synthesis/response.json')
    response['property_content'] = ''
    for requirement in response['requirements']:
        requirement['disposition'] = 'unresolved'
    path = Path(checkpoint['response_path'])
    path.write_text(json.dumps(response))
    code, result = resume(capsys, common, checkpoint, path)
    assert code == 0 and result['status'] == 'partial'
    report = pipeline.read(result['report'])
    assert report['stages']['verification']['status'] == 'skipped'
    assert report['property'] is None and report['unresolved']
    assert not calls
    path.unlink()  # Scratch response is not a durable cache dependency.
    assert exp.inspect()['stages']['synthesis']['status'] == 'current'


def test_bad_contract_fails_before_python_extraction(capsys, run_setup):
    common, exp, calls, _, _ = run_setup
    _, checkpoint = invoke(capsys, *common)
    path = Path(checkpoint['response_path'])
    path.write_text('{}')
    code, result = resume(capsys, common, checkpoint, path)
    assert code == 1 and result['error']['stage'] == 'colreg_extraction'
    assert exp.inspect()['stages']['colreg_extraction']['last_attempt']['status'] == 'failed'
    assert not (exp.folder / 'rebeca_extraction.json').exists()
    assert not calls


@pytest.mark.parametrize(('gate', 'xml_status', 'expected'), [
    ('violated', 'queue overflow', 'queue_overflow'),
    ('violated', 'assertion failed', 'violated'),
    ('unknown', 'unknown', 'unknown'),
    ('satisfied', 'satisfied', 'satisfied'),
    ('execution_failed', 'unknown', 'execution_failed'),
])
def test_verification_interpretation(tmp_path, gate, xml_status, expected):
    xml = tmp_path / 'result.xml'
    xml.write_text(f'<report><checked-property><result>{xml_status}</result></checked-property></report>')
    result = {'verification_status': gate, 'rmc_details': {}, 'optional_checks': {}}
    assert pipeline.verification_summary(result, xml)['outcome'] == expected
