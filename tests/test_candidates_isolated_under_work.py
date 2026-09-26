"""
Tests that candidate/synthesis files are isolated under the work tree
(output/work/<rule_id>/candidates/) and never written directly into the
final rule directory (output/<rule_id>/).

These tests verify the output_policy path helpers produce the correct
separation, acting as a regression guard against the original bug where
step04/step05 candidates were written into the final rule dir.
"""

from pathlib import Path

import pytest

from output_policy import (
    FinalPaths,
    WorkPaths,
    final_paths,
    report_paths,
    work_paths,
)


class TestCandidateIsolation:
    """candidates_dir must be under work/, not under the final rule dir."""

    def test_candidates_dir_is_under_work(self, tmp_path):
        wp = work_paths("Rule22", "step05", base_dir=tmp_path)
        assert "work" in wp.candidates_dir.parts

    def test_candidates_dir_not_under_final_dir(self, tmp_path):
        fp = final_paths("Rule22", base_dir=tmp_path)
        wp = work_paths("Rule22", "step05", base_dir=tmp_path)
        assert not wp.candidates_dir.is_relative_to(fp.rule_dir)

    def test_candidates_dir_name_is_candidates(self, tmp_path):
        wp = work_paths("Rule22", "step05", base_dir=tmp_path)
        assert wp.candidates_dir.name == "candidates"

    def test_attempt_dir_is_under_run_dir(self, tmp_path):
        wp = work_paths("Rule22", "run-001", attempt=3, base_dir=tmp_path)
        assert wp.attempt_dir.is_relative_to(wp.run_dir)

    def test_attempt_dir_not_under_final_dir(self, tmp_path):
        fp = final_paths("Rule22", base_dir=tmp_path)
        wp = work_paths("Rule22", "run-001", attempt=1, base_dir=tmp_path)
        assert not wp.attempt_dir.is_relative_to(fp.rule_dir)

    def test_different_rules_have_different_work_dirs(self, tmp_path):
        wp1 = work_paths("Rule22", "run-1", base_dir=tmp_path)
        wp2 = work_paths("Rule23", "run-1", base_dir=tmp_path)
        assert wp1.candidates_dir != wp2.candidates_dir
        assert wp1.run_dir != wp2.run_dir

    def test_different_run_ids_have_different_run_dirs(self, tmp_path):
        wp1 = work_paths("Rule22", "run-1", base_dir=tmp_path)
        wp2 = work_paths("Rule22", "run-2", base_dir=tmp_path)
        assert wp1.run_dir != wp2.run_dir
        assert wp1.candidates_dir == wp2.candidates_dir  # shared per rule

    def test_work_dir_separate_from_reports(self, tmp_path):
        wp = work_paths("Rule22", "run-1", base_dir=tmp_path)
        rp = report_paths("Rule22", base_dir=tmp_path)
        assert not wp.run_dir.is_relative_to(rp.report_dir)
        assert not rp.report_dir.is_relative_to(wp.run_dir)

    def test_mkdir_creates_candidates_dir(self, tmp_path):
        wp = work_paths("Rule22", "run-1", base_dir=tmp_path)
        wp.candidates_dir.mkdir(parents=True, exist_ok=True)
        assert wp.candidates_dir.is_dir()

    def test_mkdir_creates_attempt_dir(self, tmp_path):
        wp = work_paths("Rule22", "run-1", attempt=2, base_dir=tmp_path)
        wp.attempt_dir.mkdir(parents=True, exist_ok=True)
        assert wp.attempt_dir.is_dir()


class TestCleanupOutputs:
    """cleanup_outputs.py — work dirs cleaned without touching finals or reports."""

    def _setup_tree(self, tmp_path: Path) -> None:
        """Create a representative output tree."""
        # Final dir
        final = tmp_path / "Rule22"
        final.mkdir()
        (final / "Rule22.rebeca").write_text("model", encoding="utf-8")
        (final / "Rule22.property").write_text("property", encoding="utf-8")
        # Work dirs
        work = tmp_path / "work" / "Rule22"
        (work / "candidates").mkdir(parents=True)
        (work / "candidates" / "cand.rebeca").write_text("x", encoding="utf-8")
        (work / "runs" / "run-001").mkdir(parents=True)
        (work / "runs" / "run-001" / "attempt-1").mkdir()
        (work / "runs" / "run-002").mkdir(parents=True)
        # Reports dir
        reports = tmp_path / "reports" / "Rule22"
        reports.mkdir(parents=True)
        (reports / "summary.json").write_text("{}", encoding="utf-8")

    def test_cleanup_removes_work_dirs(self, tmp_path):
        from cleanup_outputs import cleanup_rule
        self._setup_tree(tmp_path)
        cleanup_rule("Rule22", tmp_path)
        work_rule = tmp_path / "work" / "Rule22"
        assert not work_rule.exists() or not any(work_rule.iterdir())

    def test_cleanup_preserves_finals(self, tmp_path):
        from cleanup_outputs import cleanup_rule
        self._setup_tree(tmp_path)
        cleanup_rule("Rule22", tmp_path)
        assert (tmp_path / "Rule22" / "Rule22.rebeca").exists()
        assert (tmp_path / "Rule22" / "Rule22.property").exists()

    def test_cleanup_preserves_reports(self, tmp_path):
        from cleanup_outputs import cleanup_rule
        self._setup_tree(tmp_path)
        cleanup_rule("Rule22", tmp_path)
        assert (tmp_path / "reports" / "Rule22" / "summary.json").exists()

    def test_keep_latest_retains_most_recent_run(self, tmp_path):
        from cleanup_outputs import cleanup_rule
        self._setup_tree(tmp_path)
        cleanup_rule("Rule22", tmp_path, keep_latest=True)
        runs_dir = tmp_path / "work" / "Rule22" / "runs"
        if runs_dir.exists():
            remaining = list(runs_dir.iterdir())
            assert len(remaining) <= 1, f"keep_latest should retain at most 1 run, found: {remaining}"

    def test_dry_run_does_not_delete(self, tmp_path):
        from cleanup_outputs import cleanup_rule
        self._setup_tree(tmp_path)
        cleanup_rule("Rule22", tmp_path, dry_run=True)
        # Work dirs must still exist after dry-run
        assert (tmp_path / "work" / "Rule22" / "candidates").exists()

    def test_nonexistent_rule_returns_zero(self, tmp_path):
        from cleanup_outputs import cleanup_rule
        result = cleanup_rule("NonExistentRule", tmp_path)
        assert result == 0
