"""Real toolchain checks: compile success and semantic success are different."""
import json
import importlib
from pathlib import Path
import pytest

rmc = importlib.import_module('skills.rebeca_tooling.scripts.run_rmc')
gate = importlib.import_module('skills.rebeca_tooling.scripts.verify_gate')


@pytest.mark.requires_rmc
@pytest.mark.parametrize('assertion,expected', [('s1.length > 0', 'satisfied'), ('s1.length < 0', 'violated')])
def test_real_gate_verdict(rmc_jar, model_file, tmp_path, assertion, expected):
    prop = tmp_path / 'model.property'
    prop.write_text('property { Assertion { Rule22: ' + assertion + '; } }')
    result = gate.run_verification_gate(rmc_jar, model_file, str(prop), 'Rule22', str(tmp_path / 'out'),
                                        skip_vacuity=True, skip_mutation=True)
    (tmp_path / 'result.json').write_text(json.dumps(result, indent=2))
    assert result['rmc_details']['cpp_compile_ok'] is True
    assert result['verification_status'] == expected
    assert result['passes_gate'] is (expected == 'satisfied')


@pytest.mark.requires_rmc
def test_real_parse_failure(rmc_jar, model_file, tmp_path):
    prop = tmp_path / 'bad.property'
    prop.write_text('property { Assertion { Rule22: this is not valid; } }')
    result = rmc.run_rmc_detailed(rmc_jar, model_file, str(prop), str(tmp_path / 'out'), run_model_outcome=True)
    assert result['rmc_exit_code'] != 0
    assert result['verification_outcome'] == 'unknown'
