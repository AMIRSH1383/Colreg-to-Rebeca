"""Deterministic reuse of authentic saved inputs; no LLM or full research run."""
import json
from pathlib import Path
import pytest
from scripts.utilities.experiment_store import Experiment, ROOT
from scripts.utilities.experiments import main as colreg_main
from scripts.extraction.rebeca_extractor import main as extract_main
from scripts.binding import semantic_binding as binding
from scripts.synthesis import synthesis


def test_managed_stages_overwrite_and_fail_safely_without_llm(tmp_path, monkeypatch):
    base = tmp_path / 'experiments'
    common = ['--rule', 'Rule22a', '--experiments-dir', str(base)]
    monkeypatch.setattr(binding, 'call_codex', lambda *a, **kw: pytest.fail('No LLM invocation'))
    monkeypatch.setattr(synthesis, 'invoke_codex', lambda *a, **kw: pytest.fail('No nested CLI'))
    source = ROOT / 'experiments/Rule22a'
    assert colreg_main(['publish-colreg'] + common + ['--source', str(source / 'colreg_extraction.json')]) == 0
    assert extract_main(common) == 0
    assert binding.main(common + ['--response', str(source / 'semantic_binding.json')]) == 0
    response = source / 'synthesis/response.json'
    assert synthesis.main(common + ['--response', str(response)]) == 0
    exp = Experiment('Rule22a', base)
    model = exp.folder / 'synthesis/model.rebeca'
    prop = exp.folder / 'synthesis/model.property'
    expected = prop.read_bytes()
    assert model.read_bytes() == (ROOT / 'inputs/rebeca/original_model.rebeca').read_bytes()
    assert prop.read_bytes() == (source / 'synthesis/model.property').read_bytes()
    # Each existing per-rule stage is updated, without new run directories.
    assert extract_main(common) == 0
    assert binding.main(common + ['--response', str(source / 'semantic_binding.json')]) == 0
    assert synthesis.main(common + ['--response', str(response)]) == 0
    assert prop.read_bytes() == expected
    broken = tmp_path / 'bad-response.json'
    broken.write_text('{}')
    assert synthesis.main(common + ['--response', str(broken)]) == 1
    assert prop.read_bytes() == expected
    state = exp.inspect()['stages']['synthesis']
    assert state['status'] == 'current'
    assert state['last_attempt']['status'] == 'failed'
    # Preparing does not replace the last successful synthesized payload.
    assert synthesis.main(common + ['--prepare-only']) == 0
    assert prop.read_bytes() == expected
    assert exp.inspect()['stages']['synthesis']['last_attempt']['status'] == 'prepared'
    # Editing an upstream input invalidates consumers, without deleting evidence.
    value = json.loads((exp.folder / 'colreg_extraction.json').read_text())
    value['extraction']['statements'][1]['value'] = 51
    (exp.folder / 'colreg_extraction.json').write_text(json.dumps(value))
    assert exp.inspect()['stages']['binding']['status'] == 'stale'
    assert synthesis.main(common + ['--response', str(response)]) == 1
    assert prop.read_bytes() == expected
    assert set(p.name for p in base.iterdir()) == {'Rule22a'}


def test_managed_verification_uses_existing_gate_and_keeps_failures(tmp_path, monkeypatch):
    import importlib
    gate = importlib.import_module('verification.verify_gate')
    from scripts.utilities.experiment_store import REQUIRED
    exp = Experiment('RuleTest', tmp_path / 'experiments')
    # Synthetic stage metadata fixture, not saved research.
    for stage in ['colreg_extraction', 'rebeca_extraction', 'binding', 'synthesis']:
        with exp.attempt(stage, []) as a:
            files = {}
            for name in REQUIRED[stage] | ({'synthesis/model.property'} if stage == 'synthesis' else set()):
                p = a.workspace / Path(name).name
                p.write_text('{}')
                files[name] = p
            a.publish(files)
    jar = tmp_path / 'fake.jar';jar.write_text('test')
    outcome = {'status': 'satisfied'}
    def run(**kwargs):
        return {'verification_status': outcome['status'], 'optional_checks': {'vacuity': 'disabled', 'mutation': 'disabled'}, 'verified': outcome['status'] == 'satisfied', 'passes_gate': outcome['status'] == 'satisfied'}
    monkeypatch.setattr(gate, 'run_verification_gate', run)
    args = ['--rule', 'RuleTest', '--experiments-dir', str(tmp_path / 'experiments'), '--jar', str(jar)]
    assert gate.main(args) == 0
    result = exp.folder / 'verification/result.json'
    previous = result.read_bytes()
    outcome['status'] = 'execution_failed'
    assert gate.main(args) == 1
    assert result.read_bytes() == previous
    assert exp.inspect()['stages']['verification']['last_attempt']['status'] == 'failed'
