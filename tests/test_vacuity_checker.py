"""
Tests for vacuity_checker.py using the real rmc.jar.

Exit-code semantics (from vacuity_checker.py docstring):
  0  Non-vacuous (meaningful property)
  1  Invalid inputs / runtime error
  2  Vacuous (property passes trivially)

safe_path() restricts all file paths to be under /tmp.
All temp dirs are created with tempfile.mkdtemp(dir=/tmp).
"""
import sys
import tempfile
from pathlib import Path

import pytest
import vacuity_checker as vacmod
from vacuity_checker import build_negated_property, check_vacuity, extract_precondition


# ===========================================================================
# Sample content (not tied to real RMC)
# ===========================================================================

# Non-vacuous: the precondition !isLong is reachable (s1.length starts at 0 < 50)
PROPERTY_NON_VACUOUS = """\
property {
  define {
    isLong = (s1.x > 5);
    lightOn = (s1.hasLight == true);
  }
  Assertion {
    Rule22: !isLong || lightOn;
  }
}
"""


# Vacuous: precondition is never reachable (length starts at 60, always > 50, so
# isLong is always true; !isLong is always false → assertion trivially holds)
PROPERTY_VACUOUS = """\
property {
  define {
    isLong = (s1.x > 5);
    lightOn = (s1.hasLight == true);
  }
  Assertion {
    Rule22: isLong || lightOn;
  }
}
"""

PROPERTY_NO_ASSERTION = """\
property {
  define {
    x = (s1.length > 1);
  }
}
"""


PROPERTY_MULTI_ASSERTION = """\
property {
    define {
        isLong = (s1.x > 5);
        lightOn = (s1.hasLight == true);
    }
    Assertion {
        Rule22: !isLong || lightOn;
        Rule23: isLong || lightOn;
    }
}
"""


# ===========================================================================
# extract_precondition — pure string logic, no RMC needed
# ===========================================================================

class TestExtractPrecondition:
    def test_extracts_negated_precondition(self):
        result = extract_precondition(PROPERTY_NON_VACUOUS)
        assert result == "!isLong || lightOn"

    def test_extracts_positive_precondition(self):
        content = "property { Assertion { Rule22: isSafe; } }"
        assert extract_precondition(content) == "isSafe"

    def test_returns_none_for_no_assertion_block(self):
        assert extract_precondition(PROPERTY_NO_ASSERTION) is None

    def test_returns_none_for_empty_string(self):
        assert extract_precondition("") is None

    def test_strips_whitespace(self):
        content = "property { Assertion {   Rule22:   x > 5  ; } }"
        result = extract_precondition(content)
        assert result is not None
        assert result.strip() == result


# ===========================================================================
# build_negated_property — pure string logic, no RMC needed
# ===========================================================================

class TestBuildNegatedProperty:
    def test_positive_precondition_gets_negated(self):
        result = build_negated_property(PROPERTY_VACUOUS, "isSafe")
        assert "!(isSafe)" in result
        assert "VacuityCheck" in result

    def test_negated_precondition_simplifies_double_negation(self):
        result = build_negated_property(PROPERTY_NON_VACUOUS, "!isLong || lightOn")
        assert "VacuityCheck" in result
        assert "!!" not in result

    def test_original_assertion_name_replaced(self):
        result = build_negated_property(PROPERTY_VACUOUS, "isSafe")
        assert "Rule22" not in result

    def test_define_block_preserved(self):
        result = build_negated_property(PROPERTY_NON_VACUOUS, "!isLong || lightOn")
        assert "define" in result
        assert "isLong" in result

    def test_vacuitycheck_label_present(self):
        result = build_negated_property(PROPERTY_VACUOUS, "isSafe")
        assert "Assertion" in result
        assert "VacuityCheck" in result

    def test_negated_with_parens_no_double_negation(self):
        result = build_negated_property(PROPERTY_VACUOUS, "!(x > 5)")
        assert "VacuityCheck" in result
        assert "!!" not in result


class TestAssertionIdEnforcement:
    def test_single_assertion_no_id_allowed(self, monkeypatch):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            base = Path(td)
            model = base / "model.rebeca"
            prop = base / "single.property"
            jar = base / "rmc.jar"
            model.write_text("reactiveclass A(1) {} main { A a():(); }", encoding="utf-8")
            prop.write_text(PROPERTY_NON_VACUOUS, encoding="utf-8")
            jar.write_text("jar", encoding="utf-8")

            calls = {"n": 0}

            def _run_stub(**_: object):
                calls["n"] += 1
                if calls["n"] == 1:  # baseline
                    return {"rmc_exit_code": 0, "verification_outcome": "satisfied"}
                return {"rmc_exit_code": 1, "verification_outcome": "cex"}

            monkeypatch.setattr(vacmod, "run_rmc_detailed", _run_stub)

            result = check_vacuity(
                jar=str(jar),
                model=str(model),
                property_file=str(prop),
                output_dir=str(base / "out"),
                timeout_seconds=10,
                assertion_id=None,
            )
            assert result["is_vacuous"] is False
            assert "Ambiguous" not in result["explanation"]

    def test_multi_assertion_no_id_fails(self, monkeypatch):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            base = Path(td)
            model = base / "model.rebeca"
            prop = base / "multi.property"
            jar = base / "rmc.jar"
            model.write_text("reactiveclass A(1) {} main { A a():(); }", encoding="utf-8")
            prop.write_text(PROPERTY_MULTI_ASSERTION, encoding="utf-8")
            jar.write_text("jar", encoding="utf-8")

            def _must_not_run(**_: object) -> int:
                raise AssertionError("run_rmc_detailed must not be called for ambiguous assertions")

            monkeypatch.setattr(vacmod, "run_rmc_detailed", _must_not_run)

            result = check_vacuity(
                jar=str(jar),
                model=str(model),
                property_file=str(prop),
                output_dir=str(base / "out"),
                timeout_seconds=10,
                assertion_id=None,
            )
            assert result["is_vacuous"] is None
            assert "Ambiguous" in result["explanation"]

    def test_multi_assertion_with_id_succeeds(self, monkeypatch):
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            base = Path(td)
            model = base / "model.rebeca"
            prop = base / "multi_with_id.property"
            jar = base / "rmc.jar"
            model.write_text("reactiveclass A(1) {} main { A a():(); }", encoding="utf-8")
            prop.write_text(PROPERTY_MULTI_ASSERTION, encoding="utf-8")
            jar.write_text("jar", encoding="utf-8")

            called = {"ran": False}
            calls = {"n": 0}

            def _run_stub(**_: object):
                called["ran"] = True
                calls["n"] += 1
                if calls["n"] == 1:  # baseline
                    return {"rmc_exit_code": 0, "verification_outcome": "satisfied"}
                return {"rmc_exit_code": 1, "verification_outcome": "cex"}

            monkeypatch.setattr(vacmod, "run_rmc_detailed", _run_stub)

            result = check_vacuity(
                jar=str(jar),
                model=str(model),
                property_file=str(prop),
                output_dir=str(base / "out"),
                timeout_seconds=10,
                assertion_id="Rule23",
            )
            assert called["ran"] is True
            assert result["is_vacuous"] is False
            assert result["assertion_id_used"] == "Rule23"
            assert "Ambiguous" not in result["explanation"]


# ===========================================================================
# check_vacuity — real rmc.jar
# ===========================================================================

@pytest.mark.requires_rmc
class TestCheckVacuityReal:
    def test_non_vacuous_property(self, rmc_jar, model_file, home_tmp):
        """Rule22: !isLong || lightOn — precondition !isLong is reachable,
        so !(!isLong || lightOn) = isLong && !lightOn must be satisfiable for
        the vacuity check to find a counterexample → non-vacuous."""
        prop = home_tmp / "nv.property"
        prop.write_text(PROPERTY_NON_VACUOUS, encoding="utf-8")
        result = check_vacuity(
            jar=rmc_jar,
            model=model_file,
            property_file=str(prop),
            output_dir=str(home_tmp / "out_nv"),
            timeout_seconds=60,
        )
        assert result["is_vacuous"] is False, (
            f"Expected non-vacuous but got: {result['explanation']}\n"
            f"secondary exit: {result['secondary_exit_code']}"
        )
        assert result["precondition_used"] is not None
        assert "NON-VACUOUS" in result["explanation"]

    def test_precondition_extracted_correctly(self, rmc_jar, model_file, home_tmp):
        prop = home_tmp / "pc.property"
        prop.write_text(PROPERTY_NON_VACUOUS, encoding="utf-8")
        result = check_vacuity(
            jar=rmc_jar,
            model=model_file,
            property_file=str(prop),
            output_dir=str(home_tmp / "out_pc"),
            timeout_seconds=60,
        )
        assert result["precondition_used"] == "!isLong || lightOn"

    def test_secondary_output_dir_reported(self, rmc_jar, model_file, home_tmp):
        prop = home_tmp / "od.property"
        prop.write_text(PROPERTY_NON_VACUOUS, encoding="utf-8")
        out = str(home_tmp / "base_out")
        result = check_vacuity(
            jar=rmc_jar, model=model_file,
            property_file=str(prop), output_dir=out,
            timeout_seconds=60,
        )
        # secondary_output_dir is now a canonical subdir, not a sibling suffix.
        # It must be a child of out (or its parent), never out + "_vacuity".
        secondary = result["secondary_output_dir"]
        assert secondary is not None
        assert not secondary.endswith("_vacuity"), (
            "secondary_output_dir must not use the legacy sibling-suffix pattern"
        )
        # Must contain the word "vacuity" (the canonical subdir name)
        assert "vacuity" in secondary

    def test_missing_property_file_returns_error(self, rmc_jar, model_file, home_tmp):
        result = check_vacuity(
            jar=rmc_jar, model=model_file,
            property_file=str(home_tmp / "nonexistent.property"),
            output_dir=str(home_tmp / "out"),
        )
        assert result["is_vacuous"] is None
        assert result["secondary_exit_code"] == 1
        assert "not found" in result["explanation"]

    def test_unparseable_property_returns_error(self, rmc_jar, model_file, home_tmp):
        bad = home_tmp / "bad.property"
        bad.write_text("this has no Assertion block", encoding="utf-8")
        result = check_vacuity(
            jar=rmc_jar, model=model_file,
            property_file=str(bad),
            output_dir=str(home_tmp / "out_bad"),
        )
        assert result["is_vacuous"] is None
        assert result["precondition_used"] is None

    def test_temp_file_cleaned_up(self, rmc_jar, model_file, home_tmp):
        """The negated-property temp file must be deleted after the RMC run."""
        prop = home_tmp / "cleanup.property"
        prop.write_text(PROPERTY_NON_VACUOUS, encoding="utf-8")

        files_before = set(Path(tempfile.gettempdir()).iterdir())
        home_files_before = set(Path("/tmp").iterdir())

        check_vacuity(
            jar=rmc_jar, model=model_file,
            property_file=str(prop),
            output_dir=str(home_tmp / "out_cleanup"),
            timeout_seconds=60,
        )

        # No new .property temp files should remain
        new_tmp = set(Path(tempfile.gettempdir()).iterdir()) - files_before
        new_home = set(Path("/tmp").iterdir()) - home_files_before
        stale = [f for f in new_tmp | new_home
                 if f.suffix == ".property" and f.exists()]
        assert stale == [], f"Stale temp property files: {stale}"


# ===========================================================================
# CLI exit codes — real rmc.jar
# ===========================================================================

@pytest.mark.requires_rmc
class TestVacuityCLI:
    def _run(self, args: list, scripts_dir: str) -> "subprocess.CompletedProcess":
        import subprocess
        return subprocess.run(
            [sys.executable, "vacuity_checker.py"] + args,
            cwd=scripts_dir,
            capture_output=True, text=True,
        )

    def test_exit_0_non_vacuous(self, rmc_jar, model_file, home_tmp):
        import subprocess
        scripts_dir = str(Path(__file__).parent.parent / "skills" / "rebeca_tooling" / "scripts")
        prop = home_tmp / "cli_nv.property"
        prop.write_text(PROPERTY_NON_VACUOUS, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, "vacuity_checker.py",
             "--jar", rmc_jar,
             "--model", model_file,
             "--property", str(prop),
             "--output-dir", str(home_tmp / "cli_out_nv"),
             "--timeout-seconds", "60"],
            cwd=scripts_dir, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_exit_1_missing_property(self, rmc_jar, model_file, home_tmp):
        import subprocess
        scripts_dir = str(Path(__file__).parent.parent / "skills" / "rebeca_tooling" / "scripts")
        result = subprocess.run(
            [sys.executable, "vacuity_checker.py",
             "--jar", rmc_jar,
             "--model", model_file,
             "--property", str(home_tmp / "nope.property"),
             "--output-dir", str(home_tmp / "cli_out_err")],
            cwd=scripts_dir, capture_output=True, text=True,
        )
        assert result.returncode == 1, f"stderr: {result.stderr}"
