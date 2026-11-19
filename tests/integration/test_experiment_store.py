"""Publication lifecycle tests; fixture payloads are not new research outputs."""
import json
from pathlib import Path
import pytest
from scripts.utilities.experiment_store import Experiment


def experiment(tmp_path):
    return Experiment('Rule22a', tmp_path / 'experiments', tmp_path / 'work')


def publish(exp, stage, inputs, files):
    with exp.attempt(stage, inputs) as a:
        mapping = {}
        for name, content in files.items():
            p = a.workspace / Path(name).name
            p.write_text(content)
            mapping[name] = p
        a.publish(mapping)


def seed(exp):
    publish(exp, 'colreg_extraction', [], {'colreg_extraction.json': 'colreg-v1'})
    publish(exp, 'rebeca_extraction', [], {'rebeca_extraction.json': 'model-v1'})
    publish(exp, 'binding', [exp.folder / 'colreg_extraction.json', exp.folder / 'rebeca_extraction.json'], {'semantic_binding.json': 'binding-v1'})
    publish(exp, 'synthesis', [exp.folder / 'semantic_binding.json'], {'synthesis/model.rebeca': 'model-v1', 'synthesis/model.property': 'property-v1', 'synthesis/report.json': '{}'})
    publish(exp, 'verification', [exp.folder / 'synthesis/model.rebeca', exp.folder / 'synthesis/model.property'], {'verification/result.json': 'result-v1'})


def test_overwrite_and_failure_preserve_last_success(tmp_path):
    exp = experiment(tmp_path)
    seed(exp)
    with pytest.raises(RuntimeError):
        with exp.attempt('synthesis', [exp.folder / 'semantic_binding.json']) as a:
            (a.workspace / 'diagnostic.log').write_text('failed attempt')
            raise RuntimeError('provider failed')
    state = exp.inspect()['stages']['synthesis']
    assert state['status'] == 'current'
    assert state['last_attempt']['status'] == 'failed'
    assert (exp.folder / 'synthesis/model.property').read_text() == 'property-v1'
    assert (exp.work_root / 'synthesis/failed/diagnostic.log').read_text() == 'failed attempt'
    publish(exp, 'synthesis', [exp.folder / 'semantic_binding.json'], {'synthesis/model.rebeca': 'model-v2', 'synthesis/report.json': '{}'})
    assert not (exp.folder / 'synthesis/model.property').exists()  # no stale leftover Property
    assert exp.inspect()['stages']['verification']['status'] == 'stale'


def test_input_changes_invalidate_only_dependent_stages(tmp_path):
    exp = experiment(tmp_path)
    seed(exp)
    publish(exp, 'colreg_extraction', [], {'colreg_extraction.json': 'colreg-v2'})
    status = {key: value['status'] for key, value in exp.inspect()['stages'].items()}
    assert status == {'colreg_extraction': 'current', 'rebeca_extraction': 'current', 'binding': 'stale', 'synthesis': 'stale', 'verification': 'stale'}
    with pytest.raises(ValueError, match='upstream'):
        with exp.attempt('verification', [exp.folder / 'synthesis/model.rebeca']):
            pytest.fail('Stale synthesis must not execute')
    assert (exp.folder / 'verification/result.json').read_text() == 'result-v1'


def test_external_input_or_manual_output_edit_detected(tmp_path):
    exp = experiment(tmp_path)
    source = tmp_path / 'source'
    source.write_text('v1')
    publish(exp, 'colreg_extraction', [source], {'colreg_extraction.json': 'saved'})
    source.write_text('v2')
    assert exp.inspect()['stages']['colreg_extraction']['status'] == 'stale'
    source.write_text('v1')
    (exp.folder / 'colreg_extraction.json').write_text('manual edit')
    assert exp.inspect()['stages']['colreg_extraction']['status'] == 'stale'


def test_concurrency_and_mutating_inputs_rejected(tmp_path):
    exp = experiment(tmp_path)
    source = tmp_path / 'source'
    source.write_text('v1')
    with pytest.raises(ValueError, match='Inputs changed'):
        with exp.attempt('colreg_extraction', [source]) as a:
            with pytest.raises(FileExistsError):
                with exp.attempt('colreg_extraction', [source]):
                    pass
            source.write_text('v2')
            result = a.workspace / 'result.json'
            result.write_text('{}')
            a.publish({'colreg_extraction.json': result})
    assert not (exp.folder / 'colreg_extraction.json').exists()
    assert exp.inspect()['stages']['colreg_extraction']['last_attempt']['status'] == 'failed'


def test_partial_publication_rolls_back(tmp_path, monkeypatch):
    import scripts.utilities.experiment_store as store
    exp = experiment(tmp_path)
    seed(exp)
    original = store.shutil.copyfile
    def fail(source, target, **kwargs):
        if Path(source).name == 'report.json' and Path(target).name.startswith('.publish-'):
            raise OSError('simulated disk failure')
        return original(source, target, **kwargs)
    monkeypatch.setattr(store.shutil, 'copyfile', fail)
    with pytest.raises(OSError):
        publish(exp, 'synthesis', [exp.folder / 'semantic_binding.json'], {'synthesis/model.rebeca': 'changed', 'synthesis/report.json': 'new'})
    assert (exp.folder / 'synthesis/model.rebeca').read_text() == 'model-v1'
    assert (exp.folder / 'synthesis/model.property').read_text() == 'property-v1'
    assert exp.inspect()['stages']['synthesis']['last_attempt']['status'] == 'failed'


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'synthesis/model.cpp', 'synthesis/statespace.xml'])
def test_no_large_or_escaping_artifacts(tmp_path, name):
    exp = experiment(tmp_path)
    seed(exp)
    with pytest.raises(ValueError):
        publish(exp, 'synthesis', [exp.folder / 'semantic_binding.json'], {'synthesis/model.rebeca': 'x', 'synthesis/report.json': '{}', name: 'bad'})
    assert (exp.folder / 'synthesis/model.rebeca').read_text() == 'model-v1'
