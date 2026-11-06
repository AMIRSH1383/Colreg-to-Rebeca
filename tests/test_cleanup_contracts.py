"""Preservation and compatibility checks for the repository migration."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import validate

ROOT = Path(__file__).resolve().parents[1]


def test_preserved_inputs_and_contracts():
    manifest = json.loads((ROOT / 'archive/rebecai/preservation.json').read_text())
    for old, checksum in manifest['sha256'].items():
        if old == 'work/Original Model.rebeca':
            new = 'inputs/rebeca/original_model.rebeca'
        elif old.startswith('work/colreg/'):
            new = old.replace('work/colreg/', 'inputs/colreg/')
        elif old.startswith('work/legacy_baseline/'):
            new = old.replace('work/legacy_baseline/', 'archive/rebecai/legacy_baseline/')
        else:
            new = old
        assert hashlib.sha256((ROOT / new).read_bytes()).hexdigest() == checksum, new


def test_agent_platform_copy():
    subprocess.run([sys.executable, 'scripts/sync_agents.py', '--check'], check=True, cwd=ROOT)


def test_all_verification_modules_importable():
    for name in ['run_rmc', 'rmc_resolver', 'rmc_result_parser', 'mutation_engine',
                 'vacuity_checker', 'verify_gate', 'output_policy', 'utils']:
        importlib.import_module('skills.rebeca_tooling.scripts.' + name)


def test_preserved_extractions_match_schema():
    schema = json.loads((ROOT / 'schemas/colreg-extractor.schema.json').read_text())
    for path in (ROOT / 'experiments').glob('*/extraction.json'):
        validate(json.loads(path.read_text()), schema)


def test_heuristic_preserves_ltl_and_equality(tmp_path):
    path = tmp_path / 'example.property'
    path.write_text('property { define { x = (a == b); } LTL { L: G(a -> b); } }')
    command = [sys.executable, 'scripts/check_rebeca_syntax.py', str(path)]
    assert subprocess.run(command, cwd=ROOT, capture_output=True).returncode == 0
    path.write_text('property { Assertion { Bad: a => b; } }')
    assert subprocess.run(command, cwd=ROOT, capture_output=True).returncode == 1
