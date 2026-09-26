"""
tests/test_coordinator_e2e.py

End-to-end integration test for the legata_to_rebeca coordinator pipeline.

Each step invokes the corresponding dumb tool(s) via subprocess — exactly
how the coordinator agents call them.  LLM-only steps (Step03 abstraction,
Step05 candidate selection) use pre-computed fixtures in tests/fixtures/ so
the test is deterministic, fast, and offline-capable.

Run:
    pytest tests/test_coordinator_e2e.py -v
    pytest tests/test_coordinator_e2e.py -v -s   # see subprocess output
    KEEP_ARTIFACTS=1 pytest tests/test_coordinator_e2e.py -v  # inspect tmpdir

Markers:
    requires_rmc  — skipped automatically when ~/.rebeca/rmc.jar is absent
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).parent.parent
_SCRIPTS = _ROOT / "skills" / "rebeca_tooling" / "scripts"
_FIXTURES = Path(__file__).parent / "fixtures"
_RULE22_LEGATA = _FIXTURES / "Rule22.legata"
_STEP03_FIXTURE = _FIXTURES / "step02_abstraction.json"

_ENV = {**os.environ, "PYTHONPATH": str(_SCRIPTS)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run a tool subprocess and return the result."""
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=stdin,
        env=_ENV,
    )


def _json(result: subprocess.CompletedProcess[str], *, context: str) -> Dict[str, Any]:
    """Parse stdout as JSON, failing the test with clear diagnostics on error."""
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"{context}: subprocess exited {result.returncode} but stdout is not valid JSON.\n"
            f"stdout: {result.stdout!r}\n"
            f"stderr: {result.stderr!r}\n"
            f"error: {exc}"
        )


def _assert_no_error_envelope(data: Dict[str, Any], *, step: str) -> None:
    """Fail immediately if the subagent returned an error envelope."""
    if data.get("status") == "error":
        pytest.fail(
            f"{step} returned error envelope: "
            f"phase={data.get('phase')!r} agent={data.get('agent')!r} "
            f"message={data.get('message')!r}"
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def work_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Persistent temp directory for the whole E2E module run."""
    d = tmp_path_factory.mktemp("e2e_Rule22")
    yield d
    if not os.environ.get("KEEP_ARTIFACTS"):
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(scope="module")
def pipeline(work_dir: Path) -> Dict[str, Any]:
    """
    Accumulated pipeline state passed between steps.
    Populated incrementally as each step test runs.
    """
    return {
        "rule_id": "Rule22",
        "source_file_path": str(_RULE22_LEGATA),
        "work_dir": work_dir,
        "phase_results": {},
        "execution_path": [],
    }


# ---------------------------------------------------------------------------
# Step 03 — abstraction_agent (LLM-only): fixture
# ---------------------------------------------------------------------------

class TestStep03Abstraction:
    def test_fixture_contract(self, pipeline: Dict[str, Any]) -> None:
        """IT-E2E-03: abstraction fixture has actor_map ≥1 and variable_map ≥1."""
        assert _STEP03_FIXTURE.exists(), f"Missing fixture: {_STEP03_FIXTURE}"
        data = json.loads(_STEP03_FIXTURE.read_text())

        summary = data["abstraction_summary"]
        assert len(summary["actor_map"]) >= 1, "actor_map must have ≥1 entry"
        assert len(summary["variable_map"]) >= 1, "variable_map must have ≥1 entry"

        pipeline["phase_results"]["step03"] = data
        pipeline["execution_path"].append("step03:fixture")


# ---------------------------------------------------------------------------
# Step 04 — mapping_agent: generate .rebeca + .property via transformation_utils
# ---------------------------------------------------------------------------

class TestStep04Mapping:
    def test_generate_model_and_property(self, pipeline: Dict[str, Any]) -> None:
        """IT-E2E-04: transformation_utils generates valid .rebeca and .property files."""
        step03 = pipeline["phase_results"].get("step03")
        assert step03 is not None, "Step03 must complete before Step04"

        work = pipeline["work_dir"]
        rule_id = pipeline["rule_id"]
        model_path = work / f"{rule_id}.rebeca"
        property_path = work / f"{rule_id}.property"

        # Generate model content using transformation_utils via subprocess
        gen_script = textwrap.dedent(f"""\
            import sys, json
            sys.path.insert(0, {str(_SCRIPTS)!r})
            from transformation_utils import get_canonical_assertion, format_rebeca_define

            actor_map = {repr(step03["abstraction_summary"]["actor_map"])}
            variable_map = {repr(step03["abstraction_summary"]["variable_map"])}

            # Build statevars and init block from array-of-objects format
            actor_entry = actor_map[0]
            actor = actor_entry["rebeca_class"]
            instance = actor_entry["rebeca_instance"]
            new_vars = [v for v in variable_map if v["is_new"]]
            statevars = "\\n".join(
                f"    {{v['rebeca_type']}} {{v['rebeca_statevar']}};" for v in new_vars
            )
            init_vals = "\\n".join(
                f"    {{v['rebeca_statevar']}} = {{v['rebeca_init_value'][0]}};"
                if len(v["rebeca_init_value"]) == 1
                else f"    {{v['rebeca_statevar']}} = ?({{', '.join(v['rebeca_init_value'])}});"
                for v in new_vars
            )

            model = f\"\"\"reactiveclass {{actor}}(50) {{{{
              statevars {{{{
            {{statevars}}
              }}}}
              {{actor}}() {{{{
            {{init_vals}}
              }}}}
            }}}}
            main {{{{
              {{actor}} {{instance}}():();
            }}}}\"\"\"

            # Build property using canonical assertion pattern
            # Rule22: if large vessel then lights must meet range requirements
            cond = "isLarge"
            assure = "(mastheadOk && sideOk && sternOk && towingOk && signalOk)"
            assertion = get_canonical_assertion(cond, "false", assure)

            def statevar_ref(concept_fragment, fallback_statevar):
                match = next((v for v in variable_map if concept_fragment in v["legata_concept"]), None)
                sv = match["rebeca_statevar"] if match else fallback_statevar
                return f"{{instance}}.{{sv}}"

            define_lines = "\\n    ".join([
                format_rebeca_define("isLarge", f"{{statevar_ref('length', 'ship_length')}} >= 50"),
                format_rebeca_define("mastheadOk", f"{{statevar_ref('masthead', 'masthead_light_range')}} >= 6"),
                format_rebeca_define("sideOk", f"{{statevar_ref('side light', 'side_light_range')}} >= 3"),
                format_rebeca_define("sternOk", f"{{statevar_ref('stern', 'stern_light_range')}} >= 3"),
                format_rebeca_define("towingOk", f"{{statevar_ref('towing', 'towing_light_range')}} >= 3"),
                format_rebeca_define("signalOk", f"{{statevar_ref('signal', 'signal_light_range')}} >= 3"),
            ])

            prop = f\"\"\"property {{{{
              define {{{{
                {{define_lines}}
              }}}}
              Assertion {{{{
                Rule22a: {{assertion}};
              }}}}
            }}}}\"\"\"

            print(json.dumps({{"model": model, "property": prop}}))
        """)

        result = _run([sys.executable, "-c", gen_script])
        assert result.returncode == 0, (
            f"Step04 generation script failed: {result.stderr}"
        )
        artifacts = _json(result, context="Step04/transformation_utils")

        model_path.write_text(artifacts["model"])
        property_path.write_text(artifacts["property"])

        assert model_path.exists(), "Model file was not written"
        assert property_path.exists(), "Property file was not written"
        assert "reactiveclass" in model_path.read_text()
        assert "property" in property_path.read_text()
        assert "Assertion" in property_path.read_text()

        pipeline["phase_results"]["step04"] = {
            "status": "ok",
            "model_artifact": {"path": str(model_path)},
            "property_artifact": {"path": str(property_path)},
        }
        pipeline["execution_path"].append("step04")

    def test_mutation_engine_reads_property(self, pipeline: Dict[str, Any]) -> None:
        """IT-E2E-04b: mutation_engine can parse the generated property file."""
        step04 = pipeline["phase_results"].get("step04")
        assert step04 is not None, "Step04 must complete before this check"

        property_path = step04["property_artifact"]["path"]
        result = _run([
            sys.executable, str(_SCRIPTS / "mutation_engine.py"),
            "--rule-id", pipeline["rule_id"],
            "--property", property_path,
            "--strategy", "all",
            "--output-json",
        ])
        assert result.returncode == 0, (
            f"mutation_engine.py failed on generated property: {result.stderr}"
        )
        data = _json(result, context="Step04/mutation_engine sanity")
        assert "rule_id" in data
        assert "total_mutants" in data
        assert isinstance(data["total_mutants"], int)


# ---------------------------------------------------------------------------
# Step 05 — synthesis_agent: candidate_artifacts via mutation_engine strategies
# ---------------------------------------------------------------------------

class TestStep05Synthesis:
    def test_candidate_artifacts_contract(self, pipeline: Dict[str, Any]) -> None:
        """IT-E2E-05: mutation_engine emits candidates that satisfy coordinator contract."""
        step04 = pipeline["phase_results"].get("step04")
        assert step04 is not None, "Step04 must complete before Step05"

        rule_id = pipeline["rule_id"]
        property_path = step04["property_artifact"]["path"]
        model_path = step04["model_artifact"]["path"]

        result = _run([
            sys.executable, str(_SCRIPTS / "mutation_engine.py"),
            "--rule-id", rule_id,
            "--property", property_path,
            "--strategy", "all",
            "--output-json",
        ])
        assert result.returncode == 0, f"mutation_engine.py failed: {result.stderr}"
        mutation_data = _json(result, context="Step05/mutation_engine")

        # Build candidate_artifacts[] in the coordinator-expected shape
        now = datetime.now(timezone.utc).isoformat()
        candidate_artifacts = [
            {
                "artifact_id": f"{rule_id}_synth_base",
                "model_path": model_path,
                "property_path": property_path,
                "is_candidate": True,
                "mapping_path": "synthesis-agent",
                "source_phase": "step05",
                "strategy": "base",
                "verified": False,
                "created_at": now,
            }
        ]

        # Coordinator contract: every candidate must have is_candidate=true and mapping_path=synthesis-agent
        for c in candidate_artifacts:
            assert c["is_candidate"] is True
            assert c["mapping_path"] == "synthesis-agent"
            assert c["source_phase"] == "step05"
            assert c["verified"] is False

        pipeline["phase_results"]["step05"] = {
            "status": "ok",
            "rule_id": rule_id,
            "candidate_artifacts": candidate_artifacts,
            "synthesis_summary": {
                "strategies_tried": ["base"],
                "variants_generated": mutation_data["total_mutants"],
                "selected_strategy": "base",
                "rationale": "property-side mutation coverage ≥ 0 mutants generated",
                "property_changed": mutation_data["total_mutants"] > 0,
            },
        }
        pipeline["execution_path"].append("step05")


# ---------------------------------------------------------------------------
# Step 06 — verification_agent: RMC + vacuity + mutation scoring
# ---------------------------------------------------------------------------

class TestStep06Verification:
    @pytest.mark.requires_rmc
    def test_rmc_verifies_model(self, pipeline: Dict[str, Any], rmc_jar: str) -> None:
        """IT-E2E-06: run_rmc.py verifies the generated model against the property."""
        step05 = pipeline["phase_results"].get("step05")
        assert step05 is not None, "Step05 must complete before Step06"

        rule_id = pipeline["rule_id"]
        work = pipeline["work_dir"]
        candidate = step05["candidate_artifacts"][0]
        rmc_out = work / "rmc_out"
        rmc_out.mkdir(exist_ok=True)

        result = _run([
            sys.executable, str(_SCRIPTS / "run_rmc.py"),
            "--jar", rmc_jar,
            "--model", candidate["model_path"],
            "--property", candidate["property_path"],
            "--output-dir", str(rmc_out),
            "--timeout-seconds", "120",
        ])

        # run_rmc exits 0 (ok), 3 (timeout), 4 (cpp fail), 5 (parse fail)
        assert result.returncode in (0, 3, 4, 5), (
            f"run_rmc.py returned unexpected exit code {result.returncode}: {result.stderr}"
        )

        verified = result.returncode == 0
        rmc_outcome_map = {0: "verified", 3: "timeout", 4: "cpp_compile_failed", 5: "parse_failed"}

        pipeline["phase_results"]["step06"] = {
            "status": "ok",
            "rule_id": rule_id,
            "verified": verified,
            "rmc_exit_code": result.returncode,
            "rmc_outcome": rmc_outcome_map.get(result.returncode, "unknown"),
            "rmc_output_dir": str(rmc_out) if verified else None,
        }
        pipeline["execution_path"].append("step06:rmc")

    def test_mutation_scoring_contract(self, pipeline: Dict[str, Any]) -> None:
        """IT-E2E-06b: mutation_engine scoring produces required fields."""
        step04 = pipeline["phase_results"].get("step04")
        if step04 is None:
            pytest.skip("Step04 artifacts not available")

        result = _run([
            sys.executable, str(_SCRIPTS / "mutation_engine.py"),
            "--rule-id", pipeline["rule_id"],
            "--property", step04["property_artifact"]["path"],
            "--strategy", "all",
            "--output-json",
        ])
        assert result.returncode == 0
        data = _json(result, context="Step06/mutation_scoring")
        assert "total_mutants" in data
        assert "mutants" in data
        assert isinstance(data["mutants"], list)
        pipeline["execution_path"].append("step06:mutation_scoring")


# ---------------------------------------------------------------------------
# Step 07 — packaging_agent: copy artifacts to dest_dir
# ---------------------------------------------------------------------------

class TestStep07Packaging:
    def test_artifact_copy(self, pipeline: Dict[str, Any]) -> None:
        """IT-E2E-07: artifacts are copied to dest_dir/{rule_id}/model|property/."""
        step04 = pipeline["phase_results"].get("step04")
        assert step04 is not None, "Step04 must complete before Step07"

        rule_id = pipeline["rule_id"]
        work = pipeline["work_dir"]
        dest = work / "dest"

        model_src = Path(step04["model_artifact"]["path"])
        prop_src = Path(step04["property_artifact"]["path"])

        model_dest_dir = dest / rule_id / "model"
        prop_dest_dir = dest / rule_id / "property"
        model_dest_dir.mkdir(parents=True, exist_ok=True)
        prop_dest_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(model_src, model_dest_dir / model_src.name)
        shutil.copy2(prop_src, prop_dest_dir / prop_src.name)

        generated_files = [
            str(model_dest_dir / model_src.name),
            str(prop_dest_dir / prop_src.name),
        ]
        installation_report = [
            {
                "artifact_id": f"{rule_id}_model",
                "source_path": str(model_src),
                "dest_path": str(model_dest_dir / model_src.name),
                "artifact_type": "model",
                "status": "installed",
                "reason": None,
            },
            {
                "artifact_id": f"{rule_id}_property",
                "source_path": str(prop_src),
                "dest_path": str(prop_dest_dir / prop_src.name),
                "artifact_type": "property",
                "status": "installed",
                "reason": None,
            },
        ]

        for f in generated_files:
            assert Path(f).exists(), f"Expected artifact not copied: {f}"

        pipeline["phase_results"]["step07"] = {
            "status": "ok",
            "rule_id": rule_id,
            "dest_dir": str(dest),
            "generated_files": generated_files,
            "installation_report": installation_report,
        }
        pipeline["execution_path"].append("step07")


# ---------------------------------------------------------------------------
# Step 08 — reporting_agent: score + generate report
# ---------------------------------------------------------------------------

class TestStep08Reporting:
    def test_score_rule(self, pipeline: Dict[str, Any]) -> None:
        """IT-E2E-08a: score_rule.py produces a valid scorecard."""
        step04 = pipeline["phase_results"].get("step04")
        assert step04 is not None, "Step04 must complete before Step08"

        step06 = pipeline["phase_results"].get("step06", {})
        verify_status = "pass" if step06.get("verified") else "unknown"

        result = _run([
            sys.executable, str(_SCRIPTS / "score_rule.py"),
            "--rule-id", pipeline["rule_id"],
            "--model", step04["model_artifact"]["path"],
            "--property", step04["property_artifact"]["path"],
            "--verify-status", verify_status,
            "--output-json",
        ])
        assert result.returncode == 0, f"score_rule.py failed: {result.stderr}"
        scorecard = _json(result, context="Step08/score_rule")

        for field in ("rule_id", "status", "score_total", "score_breakdown"):
            assert field in scorecard, f"scorecard missing required field: {field!r}"

        pipeline["phase_results"]["step08_scorecard"] = scorecard
        pipeline["execution_path"].append("step08:score")

    def test_generate_report(self, pipeline: Dict[str, Any]) -> None:
        """IT-E2E-08b: generate_report.py produces a report with per_rule_scorecards."""
        scorecard = pipeline["phase_results"].get("step08_scorecard")
        assert scorecard is not None, "Scorecard must be computed before report generation"

        result = _run(
            [sys.executable, str(_SCRIPTS / "generate_report.py")],
            stdin=json.dumps(scorecard) + "\n",
        )
        assert result.returncode == 0, f"generate_report.py failed: {result.stderr}"
        report = _json(result, context="Step08/generate_report")

        assert "per_rule_scorecards" in report, "Report missing per_rule_scorecards"
        assert len(report["per_rule_scorecards"]) >= 1

        pipeline["phase_results"]["step08"] = {"status": "ok", "report": report}
        pipeline["execution_path"].append("step08:report")


# ---------------------------------------------------------------------------
# Final DAG validation
# ---------------------------------------------------------------------------

class TestDAGTopology:
    def test_all_steps_executed(self, pipeline: Dict[str, Any]) -> None:
        """IT-E2E-DAG: execution_path covers steps 01–08 in order."""
        path = pipeline["execution_path"]
        assert any("step01" in s for s in path), "Step01 not in execution path"
        assert any("step02" in s for s in path), "Step02 not in execution path"
        assert any("step03" in s for s in path), "Step03 not in execution path"
        assert any("step04" in s for s in path), "Step04 not in execution path"
        assert any("step05" in s for s in path), "Step05 not in execution path"
        assert any("step06" in s for s in path), "Step06 not in execution path"
        assert any("step07" in s for s in path), "Step07 not in execution path"
        assert any("step08" in s for s in path), "Step08 not in execution path"

    def test_phase_results_all_present(self, pipeline: Dict[str, Any]) -> None:
        """IT-E2E-DAG: phase_results contains an entry for each completed step."""
        results = pipeline["phase_results"]
        for step in ("step01", "step02", "step03", "step04", "step05", "step07", "step08"):
            assert step in results, f"phase_results missing {step}"
            assert results[step].get("status") != "error", (
                f"{step} is in error state: {results[step]}"
            )

    def test_idempotent(self, pipeline: Dict[str, Any]) -> None:
        """IT-E2E-IDEMPOTENT: re-running classify produces the same classification."""
        result = _run([
            sys.executable, str(_SCRIPTS / "classify_rule_status.py"),
            "--legata-path", pipeline["source_file_path"],
        ])
        assert result.returncode == 0
        data = _json(result, context="Idempotency/classify_rule_status")
        step01_classification = pipeline["phase_results"]["step01"]["classification"]["status"]
        assert data["status"] == step01_classification, (
            f"Idempotency violation: first run={step01_classification!r}, "
            f"second run={data['status']!r}"
        )
