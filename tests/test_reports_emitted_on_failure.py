"""
Tests that report paths are structurally correct and always resolvable,
even when quality gates fail.

The underlying guarantee: report_paths() is a pure function that always
returns valid ReportPaths regardless of pipeline state.  Callers must
create the report_dir and write files inside a finally block so that
partial results are always visible.
"""

import json
import tempfile
from pathlib import Path

import pytest

from output_policy import ReportPaths, report_paths


# ---------------------------------------------------------------------------
# report_paths — structural invariants
# ---------------------------------------------------------------------------

class TestReportPaths:
    def test_all_paths_under_report_dir(self, tmp_path):
        rp = report_paths("COLREG-Rule22", base_dir=tmp_path)
        for attr in ("summary_json", "summary_md", "verification_json", "quality_gates_json"):
            p = getattr(rp, attr)
            assert p.is_relative_to(rp.report_dir), (
                f"{attr} ({p}) is not under report_dir ({rp.report_dir})"
            )

    def test_report_dir_contains_rule_id(self, tmp_path):
        rp = report_paths("MyRule", base_dir=tmp_path)
        assert "MyRule" in str(rp.report_dir)

    def test_summary_json_name(self, tmp_path):
        rp = report_paths("Rule22", base_dir=tmp_path)
        assert rp.summary_json.name == "summary.json"

    def test_summary_md_name(self, tmp_path):
        rp = report_paths("Rule22", base_dir=tmp_path)
        assert rp.summary_md.name == "summary.md"

    def test_verification_json_name(self, tmp_path):
        rp = report_paths("Rule22", base_dir=tmp_path)
        assert rp.verification_json.name == "verification.json"

    def test_quality_gates_json_name(self, tmp_path):
        rp = report_paths("Rule22", base_dir=tmp_path)
        assert rp.quality_gates_json.name == "quality_gates.json"

    def test_different_rules_have_different_dirs(self, tmp_path):
        rp1 = report_paths("Rule22", base_dir=tmp_path)
        rp2 = report_paths("Rule23", base_dir=tmp_path)
        assert rp1.report_dir != rp2.report_dir

    def test_invalid_rule_id_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid rule_id"):
            report_paths("../evil", base_dir=tmp_path)


# ---------------------------------------------------------------------------
# Simulate pipeline emitting reports on failure
# ---------------------------------------------------------------------------

class TestReportEmissionPattern:
    """
    Verify the intended usage pattern: reports must be written in a
    finally block so they are always emitted even when gates fail.
    """

    def _run_pipeline_with_failure(self, rule_id: str, base_dir: Path) -> None:
        """Simulate Step06 gate failure with mandatory report emission."""
        rp = report_paths(rule_id, base_dir=base_dir)
        summary = {"rule_id": rule_id, "status": "Fail", "score_total": 0}
        gates = {"verified": False, "non_vacuous": None, "mutation_score": None}
        try:
            # Simulate a gate failure
            raise RuntimeError("verification gate failed")
        finally:
            rp.report_dir.mkdir(parents=True, exist_ok=True)
            rp.summary_json.write_text(json.dumps(summary), encoding="utf-8")
            rp.quality_gates_json.write_text(json.dumps(gates), encoding="utf-8")

    def test_summary_json_exists_after_gate_failure(self, tmp_path):
        with pytest.raises(RuntimeError):
            self._run_pipeline_with_failure("COLREG-Rule22", tmp_path)
        rp = report_paths("COLREG-Rule22", base_dir=tmp_path)
        assert rp.summary_json.exists(), "summary.json must exist even after gate failure"

    def test_quality_gates_json_exists_after_gate_failure(self, tmp_path):
        with pytest.raises(RuntimeError):
            self._run_pipeline_with_failure("COLREG-Rule22", tmp_path)
        rp = report_paths("COLREG-Rule22", base_dir=tmp_path)
        assert rp.quality_gates_json.exists(), "quality_gates.json must exist after gate failure"

    def test_summary_json_content_reflects_failure(self, tmp_path):
        with pytest.raises(RuntimeError):
            self._run_pipeline_with_failure("COLREG-Rule22", tmp_path)
        rp = report_paths("COLREG-Rule22", base_dir=tmp_path)
        data = json.loads(rp.summary_json.read_text())
        assert data["status"] == "Fail"
        assert data["rule_id"] == "COLREG-Rule22"
