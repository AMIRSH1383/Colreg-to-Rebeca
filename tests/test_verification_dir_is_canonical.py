"""
Tests that verification scratch directories produced by vacuity_checker
are placed under canonical policy paths, not as sibling suffix directories.

Bug being prevented: step06 retries / vacuity runs wrote to
``<output_dir>_vacuity`` and ``<output_dir>_baseline`` (string-suffix
pattern), scattering directories next to the canonical output tree.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import output_policy
from output_policy import (
    FinalPaths,
    VerificationPaths,
    WorkPaths,
    final_paths,
    vacuity_work_dirs,
    verification_paths,
    work_paths,
)


# ---------------------------------------------------------------------------
# vacuity_work_dirs — no sibling-suffix dirs
# ---------------------------------------------------------------------------

class TestVacuityWorkDirs:
    """vacuity_work_dirs must never produce sibling _vacuity/_baseline names."""

    def test_no_suffix_pattern_without_rule_id(self, tmp_path):
        output_dir = str(tmp_path / "output" / "rule" / "verify")
        secondary, baseline = vacuity_work_dirs(output_dir)
        # Must be children, not siblings
        assert not secondary.endswith("_vacuity"), (
            f"secondary dir uses forbidden suffix pattern: {secondary}"
        )
        assert not baseline.endswith("_baseline"), (
            f"baseline dir uses forbidden suffix pattern: {baseline}"
        )

    def test_subdirs_are_inside_output_dir_without_rule_id(self, tmp_path):
        output_dir = str(tmp_path / "output" / "rule" / "verify")
        secondary, baseline = vacuity_work_dirs(output_dir)
        base = Path(output_dir)
        assert Path(secondary).is_relative_to(base), (
            f"secondary {secondary!r} is not under output_dir {output_dir!r}"
        )
        assert Path(baseline).is_relative_to(base), (
            f"baseline {baseline!r} is not under output_dir {output_dir!r}"
        )

    def test_with_rule_id_secondary_is_under_work_tree(self, tmp_path):
        output_dir = str(tmp_path / "output" / "verify")
        secondary, baseline = vacuity_work_dirs(output_dir, rule_id="COLREG-Rule22")
        # Both paths must contain "work" component
        assert "work" in Path(secondary).parts, (
            f"secondary {secondary!r} not in work tree"
        )
        assert "work" in Path(baseline).parts, (
            f"baseline {baseline!r} not in work tree"
        )

    def test_distinct_secondary_and_baseline(self, tmp_path):
        output_dir = str(tmp_path / "verify")
        secondary, baseline = vacuity_work_dirs(output_dir)
        assert secondary != baseline

    def test_invalid_rule_id_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Invalid rule_id"):
            vacuity_work_dirs(str(tmp_path), rule_id="../traversal")


# ---------------------------------------------------------------------------
# verification_paths — canonical layout
# ---------------------------------------------------------------------------

class TestVerificationPaths:
    def test_current_is_under_rule_verification_dir(self, tmp_path):
        vp = verification_paths("Rule22", "run-001", base_dir=tmp_path)
        assert vp.current_dir.is_relative_to(vp.rule_verification_dir)

    def test_run_dir_is_under_rule_verification_dir(self, tmp_path):
        vp = verification_paths("Rule22", "run-001", base_dir=tmp_path)
        assert vp.run_dir.is_relative_to(vp.rule_verification_dir)

    def test_run_dir_and_current_are_distinct(self, tmp_path):
        vp = verification_paths("Rule22", "run-001", base_dir=tmp_path)
        assert vp.run_dir != vp.current_dir

    def test_run_id_appears_in_run_dir(self, tmp_path):
        vp = verification_paths("MyRule", "abc123", base_dir=tmp_path)
        assert "abc123" in str(vp.run_dir)

    def test_current_dir_name_is_current(self, tmp_path):
        vp = verification_paths("MyRule", "abc123", base_dir=tmp_path)
        assert vp.current_dir.name == "current"

    def test_invalid_rule_id_raises(self, tmp_path):
        with pytest.raises(ValueError):
            verification_paths("../bad", "run-1", base_dir=tmp_path)

    def test_slash_in_run_id_raises(self, tmp_path):
        with pytest.raises(ValueError, match="path separators"):
            verification_paths("Rule22", "run/001", base_dir=tmp_path)


# ---------------------------------------------------------------------------
# work_paths — scratch dirs are never in the final dir
# ---------------------------------------------------------------------------

class TestWorkPaths:
    def test_work_dir_not_inside_final_dir(self, tmp_path):
        fp = final_paths("Rule22", base_dir=tmp_path)
        wp = work_paths("Rule22", "run-1", base_dir=tmp_path)
        assert not wp.run_dir.is_relative_to(fp.rule_dir), (
            "work run_dir must not be inside final rule_dir"
        )
        assert not wp.candidates_dir.is_relative_to(fp.rule_dir), (
            "work candidates_dir must not be inside final rule_dir"
        )

    def test_attempt_dir_inside_run_dir(self, tmp_path):
        wp = work_paths("Rule22", "run-1", attempt=2, base_dir=tmp_path)
        assert wp.attempt_dir.is_relative_to(wp.run_dir)
        assert wp.attempt_dir.name == "attempt-2"

    def test_attempt_below_one_raises(self, tmp_path):
        with pytest.raises(ValueError, match="attempt must be >= 1"):
            work_paths("Rule22", "run-1", attempt=0, base_dir=tmp_path)


# ---------------------------------------------------------------------------
# Step06 artifact placement — verification tree vs. work/synthesis tree
# ---------------------------------------------------------------------------

class TestStep06ArtifactPlacement:
    """Verify the distinction between the verification tree and work/synthesis tree."""

    STEP06_ARTIFACTS = [
        "rmc_details.json",
        "vacuity_check.json",
        "mutation_candidates.json",
        "mutation_killrun.json",
        "scorecard.json",
    ]

    def test_verification_run_dir_not_inside_work_tree(self, tmp_path):
        vp = verification_paths("Rule22", "run-001", base_dir=tmp_path)
        wp = work_paths("Rule22", "run-001", base_dir=tmp_path)
        assert not vp.run_dir.is_relative_to(wp.run_dir), (
            "verification run_dir must not be inside the work run_dir"
        )

    def test_work_attempt_dir_not_inside_verification_tree(self, tmp_path):
        vp = verification_paths("Rule22", "run-001", base_dir=tmp_path)
        wp = work_paths("Rule22", "run-001", attempt=1, base_dir=tmp_path)
        assert not wp.attempt_dir.is_relative_to(vp.rule_verification_dir), (
            "work attempt_dir must not be inside the verification tree"
        )

    def test_step06_artifacts_belong_under_verification_run_dir(self, tmp_path):
        vp = verification_paths("Rule22", "run-001", base_dir=tmp_path)
        vp.run_dir.mkdir(parents=True, exist_ok=True)
        for fname in self.STEP06_ARTIFACTS:
            artifact = vp.run_dir / fname
            artifact.write_text("{}", encoding="utf-8")
            assert artifact.exists(), f"{fname} must be writable under verification run_dir"
            assert artifact.is_relative_to(vp.run_dir), (
                f"{fname} must be under output/verification/<rule_id>/<run_id>/"
            )

    def test_current_dir_is_sibling_of_run_dir(self, tmp_path):
        vp = verification_paths("Rule22", "run-001", base_dir=tmp_path)
        assert vp.current_dir.parent == vp.run_dir.parent, (
            "current/ must be a sibling of the run_id directory, "
            "both under output/verification/<rule_id>/"
        )

    def test_publish_winner_to_current_dir(self, tmp_path):
        """Publishing: copying run_dir contents to current_dir is semantically valid."""
        import shutil
        vp = verification_paths("Rule22", "run-001", base_dir=tmp_path)
        vp.run_dir.mkdir(parents=True, exist_ok=True)
        (vp.run_dir / "rmc_details.json").write_text('{"phase": "step06"}', encoding="utf-8")

        vp.current_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(vp.run_dir / "rmc_details.json", vp.current_dir / "rmc_details.json")

        assert (vp.current_dir / "rmc_details.json").exists(), (
            "published artifact must exist under current/"
        )
        assert vp.current_dir.is_relative_to(vp.rule_verification_dir)

    def test_verification_run_dir_path_structure(self, tmp_path):
        vp = verification_paths("COLREG-Rule22", "run-abc", base_dir=tmp_path)
        parts = vp.run_dir.parts
        assert "verification" in parts
        assert "COLREG-Rule22" in parts
        assert "run-abc" in parts

    def test_work_attempt_dir_path_structure(self, tmp_path):
        wp = work_paths("COLREG-Rule22", "run-abc", attempt=3, base_dir=tmp_path)
        parts = wp.attempt_dir.parts
        assert "work" in parts
        assert "runs" in parts
        assert "attempt-3" in parts
        assert "verification" not in parts
