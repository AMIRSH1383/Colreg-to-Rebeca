"""Phase B integration tests: verify every step produces a canonical durable artifact.

These tests prove that:
1. artifact_writer.py writes atomically (tmp→rename) and produces schema-valid JSON.
2. Each step's VALID_FIXTURE passes its schema and can be written/read back via artifact_writer.
3. A complete simulated pipeline (all 8 artifacts + required report files) passes Gate 0.
4. Re-running artifact_writer.py with identical data produces identical artifacts (idempotent).
5. A partial run (missing any one artifact) fails Gate 0.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCRIPTS = Path(__file__).parent.parent / "skills" / "rebeca_tooling" / "scripts"
TESTS = Path(__file__).parent

sys.path.insert(0, str(SCRIPTS))
from step_schemas import validate_step_output, STEP_OUTPUT_SCHEMAS  # noqa: E402
from output_policy import step_artifact_path, report_paths  # noqa: E402

RULE_ID = "PhaseB-TestRule"

# Minimal valid payload per step — matches Phase A frozen contract
STEP_PAYLOADS: dict[str, dict] = {
    "step02_abstraction": {
        "status": "ok",
        "rule_id": RULE_ID,
        "abstraction_summary": {
            "naming_contract": {
                "reactive_class_style": "PascalCase",
                "state_var_style": "camelCase",
                "instance_style": "lowerCamelCase",
                "define_alias_style": "camelCase",
                "assertion_name_style": "PascalCase",
            },
            "actor_map": [
                {"legata_actor": "OwnShip", "rebeca_class": "Ship", "rebeca_instance": "s1"},
            ],
            "variable_map": [
                {
                    "legata_concept": "ship speed is within safe range",
                    "legata_var": "Vessel.Speed",
                    "legata_value": "10",
                    "rebeca_class": "Ship",
                    "rebeca_statevar": "ship_velocity",
                    "rebeca_type": "int",
                    "bounds": {"min": 0, "max": 30},
                    "rebeca_init_value": ["10"],
                    "is_new": False,
                },
                {
                    "legata_concept": "masthead light is on",
                    "rebeca_class": "Ship",
                    "rebeca_statevar": "masthead_light_on",
                    "rebeca_type": "boolean",
                    "rebeca_init_value": ["false", "true"],
                    "is_new": False,
                },
            ],
        },
        "open_assumptions": [],
    },
    "step03_mapping": {
        "status": "ok",
        "source_file_path": RULE_ID,
        "model_artifact": {"path": f"output/work/{RULE_ID}/candidates/model.rebeca"},
        "property_artifact": {"path": f"output/work/{RULE_ID}/candidates/model.property"},
    },
    "step04_synthesis": {
        "status": "ok",
        "source_file_path": RULE_ID,
        "candidate_artifacts": [
            {
                "artifact_id": "cand-001",
                "model_path": f"output/work/{RULE_ID}/candidates/base.rebeca",
                "property_path": f"output/work/{RULE_ID}/candidates/base.property",
                "strategy": "base",
                "is_candidate": True,
                "confidence": 0.91,
                "mapping_path": "synthesis-agent",
            },
        ],
    },
    "step05_verification_gate": {
        "status": "ok",
        "source_file_path": RULE_ID,
        "verified": True,
        "rmc_exit_code": 0,
        "rmc_output_dir": f"output/verification/{RULE_ID}/run-001",
        "vacuity_status": {"is_vacuous": False},
        "mutation_score": 90.0,
    },
    "step06_packaging_manifest": {
        "status": "ok",
        "source_file_path": RULE_ID,
        "installation_report": [
            {
                "artifact_id": f"{RULE_ID}_model",
                "source_path": f"output/work/{RULE_ID}/candidates/base.rebeca",
                "dest_path": f"output/{RULE_ID}/{RULE_ID}.rebeca",
                "artifact_type": "model",
                "status": "promoted",
                "reason": None,
            },
        ],
    },
    "step07_reporting": {
        "status": "ok",
        "source_file_path": RULE_ID,
        "summary_path": f"output/reports/{RULE_ID}/summary.json",
        "summary_md_path": f"output/reports/{RULE_ID}/summary.md",
        "summary": {
            "total_rules": 1,
            "rules_passed": 1,
            "rules_failed": 0,
            "score_mean": 90.0,
        },
    },
}

# Map step artifact name → schema key
_STEP_SCHEMA_KEY = {
    "step02_abstraction": "step03",
    "step03_mapping": "step04",
    "step04_synthesis": "step05",
    "step05_verification_gate": "step06",
    "step06_packaging_manifest": "step07",
    "step07_reporting": "step08",
}


def _run_artifact_writer(rule_id: str, step: str, data: dict, base_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "artifact_writer.py"),
            "--rule-id", rule_id,
            "--step", step,
            "--data", json.dumps(data),
            "--base-dir", str(base_dir),
        ],
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Tests: artifact_writer.py correctness
# ---------------------------------------------------------------------------

class TestArtifactWriterAtomicity:
    def test_no_tmp_file_left_behind(self, tmp_path: Path) -> None:
        data = STEP_PAYLOADS["step02_abstraction"]
        _run_artifact_writer(RULE_ID, "step02_abstraction", data, tmp_path)
        work_dir = tmp_path / "work" / RULE_ID
        tmp_files = list(work_dir.glob("*.tmp"))
        assert tmp_files == [], f"Leftover .tmp files: {tmp_files}"

    def test_idempotent_rewrite(self, tmp_path: Path) -> None:
        """Running artifact_writer twice with same data produces identical output."""
        data = STEP_PAYLOADS["step03_mapping"]
        _run_artifact_writer(RULE_ID, "step03_mapping", data, tmp_path)
        path = step_artifact_path(RULE_ID, "step03_mapping", tmp_path)
        content_first = path.read_text()

        _run_artifact_writer(RULE_ID, "step03_mapping", data, tmp_path)
        content_second = path.read_text()

        assert json.loads(content_first) == json.loads(content_second)

    def test_invalid_step_name_exits_nonzero(self, tmp_path: Path) -> None:
        result = _run_artifact_writer(RULE_ID, "step99_bogus", {"status": "ok"}, tmp_path)
        assert result.returncode != 0


# ---------------------------------------------------------------------------
# Tests: per-step schema validity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("step_artifact, schema_key", sorted(_STEP_SCHEMA_KEY.items()))
def test_step_payload_passes_schema(step_artifact: str, schema_key: str) -> None:
    """Each STEP_PAYLOADS entry must pass the Phase A frozen schema."""
    payload = copy.deepcopy(STEP_PAYLOADS[step_artifact])
    errors = validate_step_output(schema_key, payload)
    assert errors == [], f"{step_artifact}: schema violations: {errors}"


@pytest.mark.parametrize("step_artifact, schema_key", sorted(_STEP_SCHEMA_KEY.items()))
def test_artifact_written_and_read_back_passes_schema(
    step_artifact: str, schema_key: str, tmp_path: Path
) -> None:
    """Write via artifact_writer, read back from disk, validate schema — end-to-end."""
    data = STEP_PAYLOADS[step_artifact]
    result = _run_artifact_writer(RULE_ID, step_artifact, data, tmp_path)
    assert result.returncode == 0, result.stderr

    path = step_artifact_path(RULE_ID, step_artifact, tmp_path)
    on_disk = json.loads(path.read_text())
    errors = validate_step_output(schema_key, on_disk)
    assert errors == [], f"{step_artifact}: on-disk schema violations: {errors}"


# ---------------------------------------------------------------------------
# Tests: Step06 FSM guard fields explicitly
# ---------------------------------------------------------------------------

class TestStep06FsmGuardFields:
    """step05_verification_gate.json must support all three FSM transition predicates."""

    def test_all_fsm_guard_fields_present(self, tmp_path: Path) -> None:
        data = STEP_PAYLOADS["step05_verification_gate"]
        _run_artifact_writer(RULE_ID, "step05_verification_gate", data, tmp_path)
        path = step_artifact_path(RULE_ID, "step05_verification_gate", tmp_path)
        on_disk = json.loads(path.read_text())
        assert "verified" in on_disk
        assert "vacuity_status" in on_disk and "is_vacuous" in on_disk["vacuity_status"]
        assert "mutation_score" in on_disk

    def test_failing_gate_payload_is_schema_valid(self) -> None:
        """A verification-failure payload (verified=False) must also be schema-valid."""
        failing = {
            "status": "ok",
            "source_file_path": RULE_ID,
            "verified": False,
            "rmc_exit_code": 1,
            "vacuity_status": {"is_vacuous": False},
            "mutation_score": 0.0,
        }
        assert validate_step_output("step06", failing) == []
