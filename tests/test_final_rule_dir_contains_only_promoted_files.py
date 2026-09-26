"""
Tests that the final rule directory contains only promoted files
(rule_id.rebeca + rule_id.property) and that promote_candidate() enforces
this invariant.

Bug being prevented: candidate/synthesis files were written directly into
output/<rule_id>/ instead of the work/candidates/ scratch area, causing
multiple .rebeca/.property variants to accumulate there.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from output_policy import FinalPaths, final_paths, promote_candidate, work_paths


# ---------------------------------------------------------------------------
# promote_candidate — happy path
# ---------------------------------------------------------------------------

class TestPromoteCandidate:
    def _make_candidate(self, tmp_path: Path, name: str = "candidate") -> tuple[Path, Path]:
        """Create dummy candidate files in a scratch area."""
        src = tmp_path / "scratch"
        src.mkdir(parents=True, exist_ok=True)
        model = src / f"{name}.rebeca"
        prop = src / f"{name}.property"
        model.write_text("reactiveclass Ship(10) {}", encoding="utf-8")
        prop.write_text("property { Assertion { R: true; } }", encoding="utf-8")
        return model, prop

    def test_promoted_files_have_rule_id_names(self, tmp_path):
        model, prop = self._make_candidate(tmp_path)
        fp = promote_candidate(model, prop, "COLREG-Rule22", base_dir=tmp_path)
        assert fp.model.name == "COLREG-Rule22.rebeca"
        assert fp.property.name == "COLREG-Rule22.property"

    def test_promoted_files_are_inside_rule_dir(self, tmp_path):
        model, prop = self._make_candidate(tmp_path)
        fp = promote_candidate(model, prop, "Rule5", base_dir=tmp_path)
        assert fp.model.is_relative_to(fp.rule_dir)
        assert fp.property.is_relative_to(fp.rule_dir)

    def test_promoted_files_exist_on_disk(self, tmp_path):
        model, prop = self._make_candidate(tmp_path)
        fp = promote_candidate(model, prop, "Rule5", base_dir=tmp_path)
        assert fp.model.exists()
        assert fp.property.exists()

    def test_source_content_preserved(self, tmp_path):
        model, prop = self._make_candidate(tmp_path)
        original_model = model.read_text()
        original_prop = prop.read_text()
        fp = promote_candidate(model, prop, "Rule5", base_dir=tmp_path)
        assert fp.model.read_text() == original_model
        assert fp.property.read_text() == original_prop

    def test_source_files_still_exist_after_promotion(self, tmp_path):
        model, prop = self._make_candidate(tmp_path)
        promote_candidate(model, prop, "Rule5", base_dir=tmp_path)
        assert model.exists(), "promote_candidate must copy, not move"
        assert prop.exists(), "promote_candidate must copy, not move"

    def test_overwrite_true_replaces_existing(self, tmp_path):
        model, prop = self._make_candidate(tmp_path, name="v1")
        fp = promote_candidate(model, prop, "Rule5", base_dir=tmp_path)
        # Second candidate with different content
        model2, prop2 = self._make_candidate(tmp_path, name="v2")
        model2.write_text("// updated model", encoding="utf-8")
        fp2 = promote_candidate(model2, prop2, "Rule5", base_dir=tmp_path, overwrite=True)
        assert fp2.model.read_text() == "// updated model"

    def test_overwrite_false_raises_when_final_exists(self, tmp_path):
        model, prop = self._make_candidate(tmp_path)
        promote_candidate(model, prop, "Rule5", base_dir=tmp_path)
        with pytest.raises(FileExistsError):
            promote_candidate(model, prop, "Rule5", base_dir=tmp_path, overwrite=False)

    def test_missing_candidate_model_raises(self, tmp_path):
        missing = tmp_path / "ghost.rebeca"
        prop = tmp_path / "real.property"
        prop.write_text("property {}", encoding="utf-8")
        with pytest.raises(FileNotFoundError):
            promote_candidate(missing, prop, "Rule5", base_dir=tmp_path)

    def test_missing_candidate_property_raises(self, tmp_path):
        model = tmp_path / "real.rebeca"
        model.write_text("reactiveclass S(1) {}", encoding="utf-8")
        missing = tmp_path / "ghost.property"
        with pytest.raises(FileNotFoundError):
            promote_candidate(model, missing, "Rule5", base_dir=tmp_path)

    def test_invalid_rule_id_raises(self, tmp_path):
        model, prop = self._make_candidate(tmp_path)
        with pytest.raises(ValueError, match="Invalid rule_id"):
            promote_candidate(model, prop, "../traversal", base_dir=tmp_path)


# ---------------------------------------------------------------------------
# Final dir contains ONLY canonical files (no candidate noise)
# ---------------------------------------------------------------------------

class TestFinalDirIsolation:
    def test_only_two_files_after_promotion(self, tmp_path):
        """Final rule_dir must contain exactly model + property after promotion."""
        src = tmp_path / "scratch"
        src.mkdir()
        model = src / "cand.rebeca"
        prop = src / "cand.property"
        model.write_text("reactiveclass S(1) {}", encoding="utf-8")
        prop.write_text("property { Assertion { R: true; } }", encoding="utf-8")

        fp = promote_candidate(model, prop, "COLREG-Rule22", base_dir=tmp_path)

        files_in_rule_dir = list(fp.rule_dir.iterdir())
        assert len(files_in_rule_dir) == 2, (
            f"Expected exactly 2 files in rule_dir, found: {[f.name for f in files_in_rule_dir]}"
        )

    def test_work_dir_is_separate_from_final_dir(self, tmp_path):
        fp = final_paths("Rule22", base_dir=tmp_path)
        wp = work_paths("Rule22", "run-1", base_dir=tmp_path)
        assert not wp.candidates_dir.is_relative_to(fp.rule_dir)
        assert not wp.run_dir.is_relative_to(fp.rule_dir)
