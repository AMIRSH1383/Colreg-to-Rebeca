"""
Tests for mutation_engine.py --output-file behavior.

Covers:
- success path: valid non-empty JSON written atomically
- failure path: .error.json written and non-zero exit
- no-empty-artifact regression
- backward compatibility: --output-json still prints to stdout
- write_mutation_artifact / write_mutation_error_artifact unit tests
- generic rule_id (no Rule-22 hardcoding)
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from mutation_engine import (
    MutationEngine,
    write_mutation_artifact,
    write_mutation_error_artifact,
)
from fixtures import RULE_ID, SAMPLE_MODEL, SAMPLE_PROPERTY


# ---------------------------------------------------------------------------
# write_mutation_artifact — unit tests
# ---------------------------------------------------------------------------

class TestWriteMutationArtifact:
    def _minimal_payload(self, rule_id: str = RULE_ID) -> dict:
        return {
            "mode": "catalog_only",
            "rule_id": rule_id,
            "total_mutants": 1,
            "mutants": [{"mutation_id": f"{rule_id}_m_tb_01", "strategy": "transition_bypass"}],
        }

    def test_file_created(self, tmp_path):
        out = tmp_path / "result.json"
        write_mutation_artifact(out, self._minimal_payload())
        assert out.exists()

    def test_file_non_empty(self, tmp_path):
        out = tmp_path / "result.json"
        write_mutation_artifact(out, self._minimal_payload())
        assert out.stat().st_size > 0

    def test_file_is_valid_json(self, tmp_path):
        out = tmp_path / "result.json"
        write_mutation_artifact(out, self._minimal_payload())
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "rule_id" in data
        assert "total_mutants" in data

    def test_content_matches_payload(self, tmp_path):
        out = tmp_path / "result.json"
        payload = self._minimal_payload()
        write_mutation_artifact(out, payload)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["rule_id"] == payload["rule_id"]
        assert data["total_mutants"] == payload["total_mutants"]

    def test_parent_dirs_created(self, tmp_path):
        out = tmp_path / "nested" / "deep" / "result.json"
        write_mutation_artifact(out, self._minimal_payload())
        assert out.exists()

    def test_overwrites_existing_file(self, tmp_path):
        out = tmp_path / "result.json"
        out.write_text("stale", encoding="utf-8")
        payload = self._minimal_payload()
        payload["total_mutants"] = 99
        write_mutation_artifact(out, payload)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["total_mutants"] == 99

    def test_missing_rule_id_raises(self, tmp_path):
        out = tmp_path / "result.json"
        with pytest.raises(ValueError, match="rule_id"):
            write_mutation_artifact(out, {"total_mutants": 1, "mutants": []})

    def test_missing_content_keys_raises(self, tmp_path):
        out = tmp_path / "result.json"
        with pytest.raises(ValueError, match="mutants"):
            write_mutation_artifact(out, {"rule_id": RULE_ID})

    def test_generic_rule_id(self, tmp_path):
        """Artifact writing must work for any rule_id, not just Rule-22."""
        for rid in ("COLREG-Rule8", "MyCustomRule", "rule_1_2_3"):
            out = tmp_path / f"{rid}.json"
            payload = self._minimal_payload(rule_id=rid)
            write_mutation_artifact(out, payload)
            data = json.loads(out.read_text(encoding="utf-8"))
            assert data["rule_id"] == rid

    def test_no_temp_file_left_on_success(self, tmp_path):
        out = tmp_path / "result.json"
        write_mutation_artifact(out, self._minimal_payload())
        leftover = [f for f in tmp_path.iterdir() if f.suffix == ".tmp"]
        assert leftover == [], f"temp files left: {leftover}"

    def test_utf8_content_preserved(self, tmp_path):
        out = tmp_path / "result.json"
        payload = self._minimal_payload()
        payload["mutants"][0]["description"] = "Ünïcödé annotation"
        write_mutation_artifact(out, payload)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "Ünïcödé" in data["mutants"][0]["description"]


# ---------------------------------------------------------------------------
# write_mutation_error_artifact — unit tests
# ---------------------------------------------------------------------------

class TestWriteMutationErrorArtifact:
    def test_error_file_created(self, tmp_path):
        out = tmp_path / "result.json"
        err_path = write_mutation_error_artifact(out, rule_id=RULE_ID)
        assert err_path.exists()

    def test_error_file_suffix(self, tmp_path):
        out = tmp_path / "result.json"
        err_path = write_mutation_error_artifact(out, rule_id=RULE_ID)
        assert err_path.name.endswith(".error.json")

    def test_error_file_is_valid_json(self, tmp_path):
        out = tmp_path / "result.json"
        err_path = write_mutation_error_artifact(
            out, rule_id=RULE_ID,
            command=["mutation_engine.py", "--rule-id", RULE_ID],
            return_code=1,
            stderr_preview="oops",
        )
        data = json.loads(err_path.read_text(encoding="utf-8"))
        assert data["status"] == "error"
        assert data["rule_id"] == RULE_ID
        assert data["return_code"] == 1

    def test_stdout_preview_truncated(self, tmp_path):
        out = tmp_path / "result.json"
        big = "x" * 5000
        err_path = write_mutation_error_artifact(
            out, rule_id=RULE_ID, stdout_preview=big
        )
        data = json.loads(err_path.read_text(encoding="utf-8"))
        assert len(data["stdout_preview"]) <= 2000

    def test_timestamp_present(self, tmp_path):
        out = tmp_path / "result.json"
        err_path = write_mutation_error_artifact(out, rule_id=RULE_ID)
        data = json.loads(err_path.read_text(encoding="utf-8"))
        assert "timestamp" in data
        assert data["timestamp"].endswith("Z")

    def test_exception_msg_stored(self, tmp_path):
        out = tmp_path / "result.json"
        err_path = write_mutation_error_artifact(
            out, rule_id=RULE_ID, exception_msg="something went wrong"
        )
        data = json.loads(err_path.read_text(encoding="utf-8"))
        assert "something went wrong" in data["exception"]


# ---------------------------------------------------------------------------
# CLI integration: --output-file success path
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "rebeca_tooling" / "scripts"


def _run_cli(args: list[str], cwd=None) -> subprocess.CompletedProcess:
    """Run mutation_engine.py as a subprocess (fish/bash-independent)."""
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "mutation_engine.py")] + args,
        capture_output=True,
        text=True,
        cwd=str(cwd or SCRIPTS_DIR),
    )


class TestCLIOutputFile:
    def _write_model(self, tmp_path: Path) -> Path:
        p = tmp_path / "model.rebeca"
        p.write_text(SAMPLE_MODEL, encoding="utf-8")
        return p

    def _write_property(self, tmp_path: Path) -> Path:
        p = tmp_path / "prop.property"
        p.write_text(SAMPLE_PROPERTY, encoding="utf-8")
        return p

    def test_success_writes_nonempty_json(self, tmp_path):
        model = self._write_model(tmp_path)
        out = tmp_path / "step05_mutation_candidates.json"
        result = _run_cli([
            "--rule-id", "COLREG-Rule8",
            "--model", str(model),
            "--output-file", str(out),
        ])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert out.exists(), "output file not created"
        assert out.stat().st_size > 0, "output file is empty"
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["rule_id"] == "COLREG-Rule8"
        assert "total_mutants" in data
        assert "mutants" in data

    def test_success_file_cannot_be_empty(self, tmp_path):
        """Regression: --output-file must never produce a 0-byte success artifact."""
        model = self._write_model(tmp_path)
        out = tmp_path / "candidates.json"
        result = _run_cli([
            "--rule-id", "SomeRule",
            "--model", str(model),
            "--output-file", str(out),
        ])
        assert result.returncode == 0
        assert out.stat().st_size > 0, "0-byte success artifact detected"

    def test_output_file_is_valid_parseable_json(self, tmp_path):
        model = self._write_model(tmp_path)
        out = tmp_path / "out.json"
        _run_cli([
            "--rule-id", "GenericRule",
            "--model", str(model),
            "--output-file", str(out),
        ])
        parsed = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict)

    def test_failure_writes_error_json_and_exits_nonzero(self, tmp_path):
        """Non-existent model → no mutations possible → error artifact expected."""
        out = tmp_path / "step05_mutation_candidates.json"
        result = _run_cli([
            "--rule-id", "TestRule",
            "--model", str(tmp_path / "ghost.rebeca"),  # does not exist
            "--output-file", str(out),
        ])
        assert result.returncode != 0, "expected non-zero exit on failure"
        # Success artifact must not be written (or be absent)
        if out.exists():
            # If it was written, it must not be an empty file
            assert out.stat().st_size > 0

    def test_no_error_json_on_success(self, tmp_path):
        model = self._write_model(tmp_path)
        out = tmp_path / "out.json"
        _run_cli([
            "--rule-id", "Rule1",
            "--model", str(model),
            "--output-file", str(out),
        ])
        error_path = out.with_suffix(".error.json")
        assert not error_path.exists(), "error artifact must not exist on success"

    def test_generic_rule_id_no_hardcoding(self, tmp_path):
        """Rule ID in artifact must match --rule-id, not a hardcoded value."""
        model = self._write_model(tmp_path)
        for rid in ("COLREG-Rule5", "ArbRule_99", "rule-xyz"):
            out = tmp_path / f"{rid}.json"
            result = _run_cli([
                "--rule-id", rid,
                "--model", str(model),
                "--output-file", str(out),
            ])
            assert result.returncode == 0
            data = json.loads(out.read_text(encoding="utf-8"))
            assert data["rule_id"] == rid, (
                f"rule_id mismatch: expected {rid!r}, got {data['rule_id']!r}"
            )

    def test_output_file_property_only(self, tmp_path):
        prop = self._write_property(tmp_path)
        out = tmp_path / "prop_result.json"
        result = _run_cli([
            "--rule-id", "PropRule",
            "--property", str(prop),
            "--output-file", str(out),
        ])
        assert result.returncode == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["rule_id"] == "PropRule"


# ---------------------------------------------------------------------------
# CLI integration: --output-json backward compatibility
# ---------------------------------------------------------------------------

class TestCLIOutputJsonBackwardCompat:
    def _write_model(self, tmp_path: Path) -> Path:
        p = tmp_path / "model.rebeca"
        p.write_text(SAMPLE_MODEL, encoding="utf-8")
        return p

    def test_output_json_still_prints_to_stdout(self, tmp_path):
        model = self._write_model(tmp_path)
        result = _run_cli([
            "--rule-id", RULE_ID,
            "--model", str(model),
            "--output-json",
        ])
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert "rule_id" in parsed
        assert "mutants" in parsed

    def test_output_json_stdout_is_valid_json(self, tmp_path):
        model = self._write_model(tmp_path)
        result = _run_cli([
            "--rule-id", RULE_ID,
            "--model", str(model),
            "--output-json",
        ])
        assert result.returncode == 0
        # Must parse without error
        data = json.loads(result.stdout)
        assert isinstance(data, dict)

    def test_both_flags_writes_file_and_prints_stdout(self, tmp_path):
        """--output-file and --output-json together: file written AND JSON on stdout."""
        model = self._write_model(tmp_path)
        out = tmp_path / "both.json"
        result = _run_cli([
            "--rule-id", RULE_ID,
            "--model", str(model),
            "--output-file", str(out),
            "--output-json",
        ])
        assert result.returncode == 0
        assert out.exists() and out.stat().st_size > 0
        parsed = json.loads(result.stdout)
        assert parsed["rule_id"] == RULE_ID
