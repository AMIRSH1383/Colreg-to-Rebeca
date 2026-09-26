"""
Unit tests for MutationEngine — all 8 mutation strategies.

Tests are pure string transformation tests: no file I/O, no RMC required.
"""
import json
import sys
import time as pytime
from pathlib import Path


import pytest
import mutation_engine as mutation_engine_module
from mutation_engine import Mutation, MutationEngine
from mutation_engine import run_mutants

from fixtures import (
    RULE_ID,
    SAMPLE_MODEL,
    SAMPLE_PROPERTY,
    SAMPLE_PROPERTY_AND,
    SAMPLE_PROPERTY_VARS,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _ids(mutations):
    return [m.mutation_id for m in mutations]


def _strategies(mutations):
    return [m.strategy for m in mutations]


# ===========================================================================
# Mutation dataclass
# ===========================================================================

class TestMutationDataclass:
    def test_fields_present(self):
        m = Mutation(
            mutation_id="Rule-22_m_tb_01",
            strategy="transition_bypass",
            artifact="model",
            original_content="a",
            mutated_content="b",
            description="test",
        )
        assert m.mutation_id == "Rule-22_m_tb_01"
        assert m.artifact == "model"

    def test_content_unchanged(self, engine):
        """original_content must be identical to the input passed to the strategy."""
        mutations = engine.transition_bypass(SAMPLE_MODEL, RULE_ID)
        for m in mutations:
            assert m.original_content == SAMPLE_MODEL


# ===========================================================================
# Strategy: transition_bypass  (.rebeca)
# ===========================================================================

class TestTransitionBypass:
    def test_produces_at_least_one_mutant(self, engine):
        mutations = engine.transition_bypass(SAMPLE_MODEL, RULE_ID)
        assert len(mutations) >= 1

    def test_strategy_label(self, engine):
        mutations = engine.transition_bypass(SAMPLE_MODEL, RULE_ID)
        assert all(m.strategy == "transition_bypass" for m in mutations)

    def test_artifact_is_model(self, engine):
        mutations = engine.transition_bypass(SAMPLE_MODEL, RULE_ID)
        assert all(m.artifact == "model" for m in mutations)

    def test_mutation_id_prefix(self, engine):
        mutations = engine.transition_bypass(SAMPLE_MODEL, RULE_ID)
        assert all(m.mutation_id.startswith(f"{RULE_ID}_m_tb_") for m in mutations)

    def test_assignments_commented_out(self, engine):
        mutations = engine.transition_bypass(SAMPLE_MODEL, RULE_ID)
        for m in mutations:
            assert "/* " in m.mutated_content

    def test_content_differs_from_original(self, engine):
        mutations = engine.transition_bypass(SAMPLE_MODEL, RULE_ID)
        for m in mutations:
            assert m.mutated_content != m.original_content

    def test_no_msgsrv_no_mutants(self, engine):
        bare = "reactiveclass Foo(1) { statevars { int x; } }"
        mutations = engine.transition_bypass(bare, RULE_ID)
        assert mutations == []

    def test_immutability(self, engine):
        """Calling the method twice yields independent results — input not mutated."""
        r1 = engine.transition_bypass(SAMPLE_MODEL, RULE_ID)
        r2 = engine.transition_bypass(SAMPLE_MODEL, RULE_ID)
        assert len(r1) == len(r2)


# ===========================================================================
# Strategy: predicate_flip  (.rebeca)
# ===========================================================================

class TestPredicateFlip:
    def test_produces_mutants(self, engine):
        mutations = engine.predicate_flip(SAMPLE_MODEL, RULE_ID)
        assert len(mutations) >= 1

    def test_strategy_label(self, engine):
        mutations = engine.predicate_flip(SAMPLE_MODEL, RULE_ID)
        assert all(m.strategy == "predicate_flip" for m in mutations)

    def test_negation_added(self, engine):
        mutations = engine.predicate_flip(SAMPLE_MODEL, RULE_ID)
        for m in mutations:
            assert "!(" in m.mutated_content

    def test_already_negated_skipped(self, engine):
        content = "msgsrv foo() { if (!flag) { x = 1; } }"
        mutations = engine.predicate_flip(content, RULE_ID)
        # Condition is already negated — must be skipped
        assert mutations == []

    def test_mutation_id_prefix(self, engine):
        mutations = engine.predicate_flip(SAMPLE_MODEL, RULE_ID)
        assert all(m.mutation_id.startswith(f"{RULE_ID}_m_pf_") for m in mutations)

    def test_artifact_is_model(self, engine):
        assert all(m.artifact == "model" for m in engine.predicate_flip(SAMPLE_MODEL, RULE_ID))


# ===========================================================================
# Strategy: assignment_mutation  (.rebeca)
# ===========================================================================

class TestAssignmentMutation:
    def test_produces_mutants(self, engine):
        mutations = engine.assignment_mutation(SAMPLE_MODEL, RULE_ID)
        assert len(mutations) >= 1

    def test_numeric_incremented(self, engine):
        content = "msgsrv foo() { x = 5; }"
        mutations = engine.assignment_mutation(content, RULE_ID)
        assert len(mutations) == 1
        assert "6" in mutations[0].mutated_content

    def test_strategy_label(self, engine):
        mutations = engine.assignment_mutation(SAMPLE_MODEL, RULE_ID)
        assert all(m.strategy == "assignment_mutation" for m in mutations)

    def test_artifact_is_model(self, engine):
        assert all(m.artifact == "model" for m in engine.assignment_mutation(SAMPLE_MODEL, RULE_ID))

    def test_mutation_id_prefix(self, engine):
        mutations = engine.assignment_mutation(SAMPLE_MODEL, RULE_ID)
        assert all(m.mutation_id.startswith(f"{RULE_ID}_m_am_") for m in mutations)

    def test_no_numerics_no_mutants(self, engine):
        content = "msgsrv foo() { flag = true; }"
        mutations = engine.assignment_mutation(content, RULE_ID)
        assert mutations == []


# ===========================================================================
# Strategy: comparison_value_mutation  (.property)
# ===========================================================================

class TestComparisonValueMutation:
    def test_produces_mutants(self, engine):
        mutations = engine.comparison_value_mutation(SAMPLE_PROPERTY, RULE_ID)
        assert len(mutations) >= 1

    def test_numeric_incremented(self, engine):
        # SAMPLE_PROPERTY has >= 6  →  mutant should have >= 7
        mutations = engine.comparison_value_mutation(SAMPLE_PROPERTY, RULE_ID)
        assert any("7" in m.mutated_content for m in mutations)

    def test_strategy_label(self, engine):
        mutations = engine.comparison_value_mutation(SAMPLE_PROPERTY, RULE_ID)
        assert all(m.strategy == "comparison_value_mutation" for m in mutations)

    def test_artifact_is_property(self, engine):
        assert all(m.artifact == "property" for m in engine.comparison_value_mutation(SAMPLE_PROPERTY, RULE_ID))

    def test_no_define_block_yields_no_mutants(self, engine):
        content = "property { Assertion { R: x > 1; } }"
        mutations = engine.comparison_value_mutation(content, RULE_ID)
        assert mutations == []

    def test_mutation_id_prefix(self, engine):
        mutations = engine.comparison_value_mutation(SAMPLE_PROPERTY, RULE_ID)
        assert all(m.mutation_id.startswith(f"{RULE_ID}_m_cvm_") for m in mutations)


# ===========================================================================
# Strategy: boolean_predicate_negation  (.property)
# ===========================================================================

class TestBooleanPredicateNegation:
    def test_produces_mutants(self, engine):
        mutations = engine.boolean_predicate_negation(SAMPLE_PROPERTY, RULE_ID)
        assert len(mutations) >= 1

    def test_negation_prefix_added(self, engine):
        mutations = engine.boolean_predicate_negation(SAMPLE_PROPERTY, RULE_ID)
        for m in mutations:
            assert "!" in m.mutated_content

    def test_strategy_label(self, engine):
        mutations = engine.boolean_predicate_negation(SAMPLE_PROPERTY, RULE_ID)
        assert all(m.strategy == "boolean_predicate_negation" for m in mutations)

    def test_artifact_is_property(self, engine):
        assert all(m.artifact == "property" for m in engine.boolean_predicate_negation(SAMPLE_PROPERTY, RULE_ID))

    def test_mutation_id_prefix(self, engine):
        mutations = engine.boolean_predicate_negation(SAMPLE_PROPERTY, RULE_ID)
        assert all(m.mutation_id.startswith(f"{RULE_ID}_m_bpn_") for m in mutations)


# ===========================================================================
# Strategy: assertion_negation  (.property)
# ===========================================================================

class TestAssertionNegation:
    def test_produces_one_mutant_per_assertion(self, engine):
        mutations = engine.assertion_negation(SAMPLE_PROPERTY, RULE_ID)
        assert len(mutations) == 1  # one assertion in SAMPLE_PROPERTY

    def test_negation_added(self, engine):
        # Use a positive assertion so negation is added (not removed)
        content = "property { Assertion { Rule22: isSafe; } }"
        mutations = engine.assertion_negation(content, RULE_ID)
        assert len(mutations) == 1
        assert "!" in mutations[0].mutated_content

    def test_negation_removed_when_present(self, engine):
        # SAMPLE_PROPERTY has '!hasLightOn || rangeOk' → toggle removes the '!'
        mutations = engine.assertion_negation(SAMPLE_PROPERTY, RULE_ID)
        assert mutations[0].mutated_content != mutations[0].original_content

    def test_double_negation_removed(self, engine):
        content = "property { Assertion { Rule22: !someFlag; } }"
        mutations = engine.assertion_negation(content, RULE_ID)
        # Original has ! — mutant should remove it
        assert len(mutations) == 1
        assert "!!" not in mutations[0].mutated_content

    def test_strategy_label(self, engine):
        mutations = engine.assertion_negation(SAMPLE_PROPERTY, RULE_ID)
        assert all(m.strategy == "assertion_negation" for m in mutations)

    def test_artifact_is_property(self, engine):
        assert all(m.artifact == "property" for m in engine.assertion_negation(SAMPLE_PROPERTY, RULE_ID))

    def test_mutation_id_prefix(self, engine):
        mutations = engine.assertion_negation(SAMPLE_PROPERTY, RULE_ID)
        assert all(m.mutation_id.startswith(f"{RULE_ID}_m_an_") for m in mutations)


# ===========================================================================
# Strategy: assertion_predicate_inversion  (.property)
# ===========================================================================

class TestAssertionPredicateInversion:
    def test_produces_mutants(self, engine):
        mutations = engine.assertion_predicate_inversion(SAMPLE_PROPERTY, RULE_ID)
        assert len(mutations) >= 1

    def test_negated_term_present(self, engine):
        mutations = engine.assertion_predicate_inversion(SAMPLE_PROPERTY, RULE_ID)
        for m in mutations:
            assert "!" in m.mutated_content

    def test_keywords_not_negated(self, engine):
        """LTL keywords like G, F, X should not appear as !G etc."""
        content = "property { Assertion { Rule22: G(isSafe); } }"
        mutations = engine.assertion_predicate_inversion(content, RULE_ID)
        for m in mutations:
            assert "!G" not in m.mutated_content

    def test_strategy_label(self, engine):
        mutations = engine.assertion_predicate_inversion(SAMPLE_PROPERTY, RULE_ID)
        assert all(m.strategy == "assertion_predicate_inversion" for m in mutations)

    def test_mutation_id_prefix(self, engine):
        mutations = engine.assertion_predicate_inversion(SAMPLE_PROPERTY, RULE_ID)
        assert all(m.mutation_id.startswith(f"{RULE_ID}_m_api_") for m in mutations)


# ===========================================================================
# Strategy: logical_swap  (.property)
# ===========================================================================

class TestLogicalSwap:
    def test_and_becomes_or(self, engine):
        mutations = engine.logical_swap(SAMPLE_PROPERTY_AND, RULE_ID)
        assert any("||" in m.mutated_content for m in mutations)

    def test_or_becomes_and(self, engine):
        content = "property { Assertion { Rule22: a || b; } }"
        mutations = engine.logical_swap(content, RULE_ID)
        assert len(mutations) == 1
        assert "&&" in mutations[0].mutated_content

    def test_no_operator_yields_no_mutants(self, engine):
        content = "property { Assertion { Rule22: isSafe; } }"
        mutations = engine.logical_swap(content, RULE_ID)
        assert mutations == []

    def test_strategy_label(self, engine):
        mutations = engine.logical_swap(SAMPLE_PROPERTY_AND, RULE_ID)
        assert all(m.strategy == "logical_swap" for m in mutations)

    def test_artifact_is_property(self, engine):
        assert all(m.artifact == "property" for m in engine.logical_swap(SAMPLE_PROPERTY_AND, RULE_ID))

    def test_mutation_id_prefix(self, engine):
        mutations = engine.logical_swap(SAMPLE_PROPERTY_AND, RULE_ID)
        assert all(m.mutation_id.startswith(f"{RULE_ID}_m_ls_") for m in mutations)

    def test_one_mutant_per_operator(self, engine):
        content = "property { Assertion { R: a && b && c; } }"
        mutations = engine.logical_swap(content, RULE_ID)
        assert len(mutations) == 2


# ===========================================================================
# Strategy: variable_swap  (.property)
# ===========================================================================

class TestVariableSwap:
    def test_produces_mutants(self, engine):
        mutations = engine.variable_swap(SAMPLE_PROPERTY_VARS, RULE_ID)
        assert len(mutations) >= 1

    def test_variable_replaced(self, engine):
        mutations = engine.variable_swap(SAMPLE_PROPERTY_VARS, RULE_ID)
        for m in mutations:
            assert "ship." in m.mutated_content

    def test_no_pairs_no_mutants(self, engine):
        content = "property { Assertion { Rule22: ship.speed > 5; } }"
        mutations = engine.variable_swap(content, RULE_ID)
        assert mutations == []  # only one var for actor 'ship'

    def test_strategy_label(self, engine):
        mutations = engine.variable_swap(SAMPLE_PROPERTY_VARS, RULE_ID)
        assert all(m.strategy == "variable_swap" for m in mutations)

    def test_artifact_is_property(self, engine):
        assert all(m.artifact == "property" for m in engine.variable_swap(SAMPLE_PROPERTY_VARS, RULE_ID))

    def test_mutation_id_prefix(self, engine):
        mutations = engine.variable_swap(SAMPLE_PROPERTY_VARS, RULE_ID)
        assert all(m.mutation_id.startswith(f"{RULE_ID}_m_vs_") for m in mutations)


# ===========================================================================
# Batch methods
# ===========================================================================

class TestBatchMethods:
    def test_mutate_model_returns_all_model_strategies(self, engine):
        mutations = engine.mutate_model(SAMPLE_MODEL, RULE_ID)
        strategies = set(m.strategy for m in mutations)
        assert strategies >= {"transition_bypass", "predicate_flip", "assignment_mutation"}

    def test_mutate_property_returns_all_property_strategies(self, engine):
        mutations = engine.mutate_property(SAMPLE_PROPERTY, RULE_ID)
        strategies = set(m.strategy for m in mutations)
        # Only strategies that produce at least one mutant on SAMPLE_PROPERTY
        assert "assertion_negation" in strategies
        assert "comparison_value_mutation" in strategies

    def test_all_artifacts_are_model_in_mutate_model(self, engine):
        mutations = engine.mutate_model(SAMPLE_MODEL, RULE_ID)
        assert all(m.artifact == "model" for m in mutations)

    def test_all_artifacts_are_property_in_mutate_property(self, engine):
        mutations = engine.mutate_property(SAMPLE_PROPERTY, RULE_ID)
        assert all(m.artifact == "property" for m in mutations)

    def test_mutation_ids_unique_within_batch(self, engine):
        mutations = engine.mutate_model(SAMPLE_MODEL, RULE_ID)
        ids = _ids(mutations)
        assert len(ids) == len(set(ids)), "Duplicate mutation IDs found"


# ===========================================================================
# CLI exit codes
# ===========================================================================

class TestCLI:
    def test_exit_0_with_valid_files(self):
        # safe_path() restricts to paths under home dir; use tempfile inside ~
        import json
        import subprocess
        import tempfile
        home = Path.home()
        with tempfile.TemporaryDirectory(dir=home) as td:
            model = Path(td) / "model.rebeca"
            prop = Path(td) / "model.property"
            model.write_text(SAMPLE_MODEL)
            prop.write_text(SAMPLE_PROPERTY)
            scripts_dir = str(Path(__file__).parent.parent / "skills" / "rebeca_tooling" / "scripts")
            result = subprocess.run(
                [sys.executable, "mutation_engine.py",
                 "--rule-id", "Rule-22",
                 "--model", str(model),
                 "--property", str(prop),
                 "--output-json"],
                cwd=scripts_dir,
                capture_output=True, text=True,
            )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["rule_id"] == "Rule-22"
        assert data["total_mutants"] >= 1

    def test_exit_1_no_files(self):
        import subprocess
        scripts_dir = str(Path(__file__).parent.parent / "skills" / "rebeca_tooling" / "scripts")
        result = subprocess.run(
            [sys.executable, "mutation_engine.py", "--rule-id", "Rule-22"],
            cwd=scripts_dir,
            capture_output=True, text=True,
        )
        assert result.returncode == 1


class TestCLIOutputMode:
    def test_catalog_only_json_has_mode_field(self, monkeypatch, capsys):
        import tempfile

        home = Path.home()
        with tempfile.TemporaryDirectory(dir=home) as td:
            model = Path(td) / "model.rebeca"
            model.write_text(SAMPLE_MODEL, encoding="utf-8")

            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "mutation_engine.py",
                    "--rule-id",
                    "Rule-22",
                    "--model",
                    str(model),
                    "--output-json",
                ],
            )

            with pytest.raises(SystemExit) as exc:
                mutation_engine_module.main()

        assert exc.value.code == 0
        out, _ = capsys.readouterr()
        payload = json.loads(out)
        assert payload["mode"] == "catalog_only"

    def test_kill_run_json_has_mode_field(self, monkeypatch, capsys):
        import tempfile

        home = Path.home()
        with tempfile.TemporaryDirectory(dir=home) as td:
            model = Path(td) / "model.rebeca"
            model.write_text(SAMPLE_MODEL, encoding="utf-8")

            monkeypatch.setattr(
                mutation_engine_module,
                "run_mutants",
                lambda **_: {
                    "total": 1,
                    "killed": 1,
                    "survived": 0,
                    "errors": 0,
                    "mutation_score": 100.0,
                    "mutant_results": [],
                },
            )

            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "mutation_engine.py",
                    "--rule-id",
                    "Rule-22",
                    "--model",
                    str(model),
                    "--output-json",
                    "--run-with-jar",
                    str(model),
                    "--run-with-model",
                    str(model),
                    "--run-with-property",
                    str(model),
                ],
            )

            with pytest.raises(SystemExit) as exc:
                mutation_engine_module.main()

        assert exc.value.code == 0
        out, _ = capsys.readouterr()
        payload = json.loads(out)
        assert payload["mode"] == "kill_run"

    def test_catalog_only_stderr_hint(self, monkeypatch, capsys):
        import tempfile

        home = Path.home()
        with tempfile.TemporaryDirectory(dir=home) as td:
            model = Path(td) / "model.rebeca"
            model.write_text(SAMPLE_MODEL, encoding="utf-8")

            monkeypatch.setattr(
                sys,
                "argv",
                [
                    "mutation_engine.py",
                    "--rule-id",
                    "Rule-22",
                    "--model",
                    str(model),
                ],
            )

            with pytest.raises(SystemExit) as exc:
                mutation_engine_module.main()

        assert exc.value.code == 0
        _, err = capsys.readouterr()
        assert "[mutation_engine]" in err

    def test_exit_1_missing_model_file(self, tmp_path):
        import subprocess
        scripts_dir = str(Path(__file__).parent.parent / "skills" / "rebeca_tooling" / "scripts")
        result = subprocess.run(
            [sys.executable, "mutation_engine.py",
             "--rule-id", "Rule-22",
             "--model", str(tmp_path / "nonexistent.rebeca")],
            cwd=scripts_dir,
            capture_output=True, text=True,
        )
        assert result.returncode == 1


class TestKillRunGuardrails:
    def _mk_mutations(self, n: int, artifact: str = "model"):
        return [
            Mutation(
                mutation_id=f"Rule-22_m_x_{i:02d}",
                strategy="dummy",
                artifact=artifact,
                original_content="x",
                mutated_content="y",
                description="d",
            )
            for i in range(n)
        ]

    def test_max_mutants_caps_execution(self, monkeypatch):
        import tempfile

        calls = {"count": 0}

        def _run_stub(*args, **kwargs):
            calls["count"] += 1
            # First call is baseline, subsequent calls are mutants.
            if calls["count"] == 1:
                return {"rmc_exit_code": 0, "verification_outcome": "satisfied"}
            return {"rmc_exit_code": 1, "verification_outcome": "cex"}

        monkeypatch.setattr(mutation_engine_module, "run_rmc_detailed", _run_stub)

        with tempfile.TemporaryDirectory(dir=Path.home()) as td:
            base = Path(td)
            jar = base / "rmc.jar"
            model = base / "model.rebeca"
            prop = base / "model.property"
            jar.write_text("jar", encoding="utf-8")
            model.write_text(SAMPLE_MODEL, encoding="utf-8")
            prop.write_text(SAMPLE_PROPERTY, encoding="utf-8")

            result = run_mutants(
                mutations=self._mk_mutations(10, artifact="model"),
                jar=str(jar),
                model_path=model,
                property_path=prop,
                timeout_seconds=5,
                max_mutants=3,
                total_timeout=600,
                seed=42,
            )

        # baseline + max_mutants executions
        assert calls["count"] == 4
        assert result["sampled"] is True
        assert result["total_generated"] == 10
        assert result["total_run"] == 3

    def test_sampling_is_reproducible(self, monkeypatch):
        import tempfile

        calls = {"count": 0}

        def _run_stub(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return {"rmc_exit_code": 0, "verification_outcome": "satisfied"}
            return {"rmc_exit_code": 1, "verification_outcome": "cex"}

        monkeypatch.setattr(mutation_engine_module, "run_rmc_detailed", _run_stub)

        with tempfile.TemporaryDirectory(dir=Path.home()) as td:
            base = Path(td)
            jar = base / "rmc.jar"
            model = base / "model.rebeca"
            prop = base / "model.property"
            jar.write_text("jar", encoding="utf-8")
            model.write_text(SAMPLE_MODEL, encoding="utf-8")
            prop.write_text(SAMPLE_PROPERTY, encoding="utf-8")

            mutations = self._mk_mutations(10, artifact="model")
            r1 = run_mutants(
                mutations=mutations,
                jar=str(jar),
                model_path=model,
                property_path=prop,
                timeout_seconds=5,
                max_mutants=4,
                total_timeout=600,
                seed=99,
            )
            r2 = run_mutants(
                mutations=mutations,
                jar=str(jar),
                model_path=model,
                property_path=prop,
                timeout_seconds=5,
                max_mutants=4,
                total_timeout=600,
                seed=99,
            )

        ids1 = [row["mutation_id"] for row in r1["mutant_results"]]
        ids2 = [row["mutation_id"] for row in r2["mutant_results"]]
        assert ids1 == ids2

    def test_total_timeout_stops_loop(self, monkeypatch):
        import tempfile

        calls = {"count": 0}

        def _slow_run(*args, **kwargs):
            calls["count"] += 1
            pytime.sleep(1)
            if calls["count"] == 1:
                return {"rmc_exit_code": 0, "verification_outcome": "satisfied"}
            return {"rmc_exit_code": 1, "verification_outcome": "cex"}

        monkeypatch.setattr(mutation_engine_module, "run_rmc_detailed", _slow_run)

        with tempfile.TemporaryDirectory(dir=Path.home()) as td:
            base = Path(td)
            jar = base / "rmc.jar"
            model = base / "model.rebeca"
            prop = base / "model.property"
            jar.write_text("jar", encoding="utf-8")
            model.write_text(SAMPLE_MODEL, encoding="utf-8")
            prop.write_text(SAMPLE_PROPERTY, encoding="utf-8")

            result = run_mutants(
                mutations=self._mk_mutations(6, artifact="model"),
                jar=str(jar),
                model_path=model,
                property_path=prop,
                timeout_seconds=5,
                max_mutants=50,
                total_timeout=2,
                seed=42,
            )

        assert result["budget_exceeded"] is True
        assert result["total_run"] < result["total_generated"]

    def test_budget_exceeded_mutants_marked(self, monkeypatch):
        import tempfile

        calls = {"count": 0}

        def _slow_run(*args, **kwargs):
            calls["count"] += 1
            pytime.sleep(1)
            if calls["count"] == 1:
                return {"rmc_exit_code": 0, "verification_outcome": "satisfied"}
            return {"rmc_exit_code": 1, "verification_outcome": "cex"}

        monkeypatch.setattr(mutation_engine_module, "run_rmc_detailed", _slow_run)

        with tempfile.TemporaryDirectory(dir=Path.home()) as td:
            base = Path(td)
            jar = base / "rmc.jar"
            model = base / "model.rebeca"
            prop = base / "model.property"
            jar.write_text("jar", encoding="utf-8")
            model.write_text(SAMPLE_MODEL, encoding="utf-8")
            prop.write_text(SAMPLE_PROPERTY, encoding="utf-8")

            result = run_mutants(
                mutations=self._mk_mutations(5, artifact="model"),
                jar=str(jar),
                model_path=model,
                property_path=prop,
                timeout_seconds=5,
                max_mutants=50,
                total_timeout=2,
                seed=42,
            )

        outcomes = [row["outcome"] for row in result["mutant_results"]]
        assert "budget_exceeded" in outcomes
        expected_budget_count = result["total_generated"] - result["total_run"]
        assert outcomes.count("budget_exceeded") == expected_budget_count

    def test_sampling_message_emitted_to_stderr(self, monkeypatch, capsys):
        import tempfile

        calls = {"count": 0}

        def _run_stub(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return {"rmc_exit_code": 0, "verification_outcome": "satisfied"}
            return {"rmc_exit_code": 1, "verification_outcome": "cex"}

        monkeypatch.setattr(mutation_engine_module, "run_rmc_detailed", _run_stub)

        with tempfile.TemporaryDirectory(dir=Path.home()) as td:
            base = Path(td)
            jar = base / "rmc.jar"
            model = base / "model.rebeca"
            prop = base / "model.property"
            jar.write_text("jar", encoding="utf-8")
            model.write_text(SAMPLE_MODEL, encoding="utf-8")
            prop.write_text(SAMPLE_PROPERTY, encoding="utf-8")

            run_mutants(
                mutations=self._mk_mutations(8, artifact="model"),
                jar=str(jar),
                model_path=model,
                property_path=prop,
                timeout_seconds=5,
                max_mutants=3,
                total_timeout=600,
                seed=42,
            )

        out, err = capsys.readouterr()
        assert out == ""
        assert "[mutation_engine] Sampling 3 of 8 mutants (--max-mutants=3)" in err

    def test_total_timeout_message_emitted_to_stderr(self, monkeypatch, capsys):
        import tempfile

        calls = {"count": 0}

        def _slow_run(*args, **kwargs):
            calls["count"] += 1
            pytime.sleep(1)
            if calls["count"] == 1:
                return {"rmc_exit_code": 0, "verification_outcome": "satisfied"}
            return {"rmc_exit_code": 1, "verification_outcome": "cex"}

        monkeypatch.setattr(mutation_engine_module, "run_rmc_detailed", _slow_run)

        with tempfile.TemporaryDirectory(dir=Path.home()) as td:
            base = Path(td)
            jar = base / "rmc.jar"
            model = base / "model.rebeca"
            prop = base / "model.property"
            jar.write_text("jar", encoding="utf-8")
            model.write_text(SAMPLE_MODEL, encoding="utf-8")
            prop.write_text(SAMPLE_PROPERTY, encoding="utf-8")

            run_mutants(
                mutations=self._mk_mutations(5, artifact="model"),
                jar=str(jar),
                model_path=model,
                property_path=prop,
                timeout_seconds=5,
                max_mutants=50,
                total_timeout=2,
                seed=42,
            )

        out, err = capsys.readouterr()
        assert out == ""
        assert "[mutation_engine] Total timeout reached after" in err
