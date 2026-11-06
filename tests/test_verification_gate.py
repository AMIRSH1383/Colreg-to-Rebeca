"""Regression protection for semantic verdicts and optional-check uncertainty."""
import importlib
import json
from pathlib import Path

import pytest
from jsonschema import validate

gate = importlib.import_module('skills.rebeca_tooling.scripts.verify_gate')


def baseline(outcome='satisfied', compiled=True, error=None):
    return {'rmc_exit_code': 0 if compiled else 4,
            'rmc_outcome': 'verified' if compiled else 'cpp_compile_failed',
            'cpp_compile_ok': compiled, 'verification_outcome': outcome,
            'model_out': {'executed': True, 'exit_code': 0, 'error': error}}


@pytest.mark.parametrize('outcome,compiled,error,status,passed', [
    ('satisfied', True, None, 'satisfied', True),
    ('cex', True, None, 'violated', False),
    ('unknown', True, None, 'unknown', False),
    ('unknown', False, None, 'compilation_failed', False),
    ('unknown', True, 'timeout', 'execution_failed', False),
])
def test_semantic_gate(monkeypatch, tmp_path, outcome, compiled, error, status, passed):
    monkeypatch.setattr(gate, 'run_rmc_detailed', lambda **kw: baseline(outcome, compiled, error))
    result = gate.run_verification_gate('jar', 'model', 'prop', 'R', str(tmp_path),
                                        skip_vacuity=True, skip_mutation=True)
    assert result['passes_gate'] is passed
    assert result['verified'] is passed
    assert result['verification_status'] == status
    assert result['optional_checks'] == {'vacuity': 'disabled', 'mutation': 'disabled'}
    validate(result, json.loads(Path('schemas/verification.schema.json').read_text()))


@pytest.mark.parametrize('vacuous,expected', [(False, 'passed'), (True, 'failed'), (None, 'unknown')])
def test_vacuity_unknown_is_not_disabled(monkeypatch, tmp_path, vacuous, expected):
    monkeypatch.setattr(gate, 'run_rmc_detailed', lambda **kw: baseline())
    monkeypatch.setattr(gate, 'check_vacuity', lambda **kw: {'is_vacuous': vacuous})
    result = gate.run_verification_gate('jar', 'model', 'prop', 'R', str(tmp_path), skip_mutation=True)
    assert result['optional_checks']['vacuity'] == expected
    assert result['passes_gate'] is (vacuous is False)


@pytest.mark.parametrize('errors,budget,total,score,expected', [
    (0, False, 4, 100, 'passed'), (1, False, 4, 100, 'unknown'),
    (0, True, 4, 100, 'unknown'), (0, False, 0, 100, 'unknown'),
    (0, False, 4, 25, 'failed'),
])
def test_mutation_uncertainty(monkeypatch, tmp_path, errors, budget, total, score, expected):
    model = tmp_path / 'm'; model.write_text('model')
    prop = tmp_path / 'p'; prop.write_text('property')
    monkeypatch.setattr(gate, 'run_rmc_detailed', lambda **kw: baseline())
    monkeypatch.setattr(gate.MutationEngine, 'mutate_model', lambda *a: [])
    monkeypatch.setattr(gate.MutationEngine, 'mutate_property', lambda *a: [])
    monkeypatch.setattr(gate, 'run_mutants', lambda **kw: {
        'baseline_outcome': 'satisfied', 'errors': errors, 'budget_exceeded': budget,
        'total_run': total, 'mutation_score': score})
    result = gate.run_verification_gate('jar', str(model), str(prop), 'R', str(tmp_path), skip_vacuity=True)
    assert result['optional_checks']['mutation'] == expected
    assert result['passes_gate'] is (expected == 'passed')


def test_atomic_output_creates_parent(tmp_path):
    out = tmp_path / 'new' / 'nested' / 'result.json'
    gate._write_atomic(out, {'ok': True})
    assert json.loads(out.read_text()) == {'ok': True}


def test_execution_error_cannot_pass_with_positive_artifact(monkeypatch, tmp_path):
    details = baseline()
    details['model_out']['exit_code'] = 2
    monkeypatch.setattr(gate, 'run_rmc_detailed', lambda **kw: details)
    result = gate.run_verification_gate('jar', 'model', 'prop', 'R', str(tmp_path),
                                        skip_vacuity=True, skip_mutation=True)
    assert result['verification_status'] == 'execution_failed'
    assert result['passes_gate'] is False
