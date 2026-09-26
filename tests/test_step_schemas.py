"""Tests for step-boundary contract validation helpers."""

from __future__ import annotations

import copy
import json

import pytest

from skills.rebeca_tooling.scripts import assert_step_output, validate_step_output


VALID_FIXTURES: dict[str, dict[str, object]] = {
    "step01": {
        "status": "ok",
        "source_file_path": "Rule-22",
        "snapshot_path": "/tmp/snapshot.json",
        "rmc": {"jar": "/tmp/rmc.jar", "version": "2.14"},
    },
    "step02": {
        "status": "ok",
        "routing": {"path": "normal", "eligible_for_mapping": True},
        "classification": {
            "status": "formalized",
            "evidence": ["clause found"],
            "defects": [],
        },
    },
    "step03": {
        "status": "ok",
        "rule_id": "Rule-22",
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
                    "legata_concept": "ship length determines light requirements",
                    "legata_var": "Vessel.Length",
                    "legata_value": "50",
                    "rebeca_class": "Ship",
                    "rebeca_statevar": "ship_length",
                    "rebeca_type": "int",
                    "bounds": {"min": 0, "max": 300},
                    "rebeca_init_value": ["60"],
                    "is_new": False,
                },
            ],
        },
        "open_assumptions": [],
    },
    "step04": {
        "status": "ok",
        "model_artifact": {"path": "/tmp/model.rebeca"},
        "property_artifact": {"path": "/tmp/model.property"},
    },
    "step05": {
        "status": "ok",
        "candidate_artifacts": [
            {
                "model_path": "/tmp/candidate.rebeca",
                "property_path": "/tmp/candidate.property",
                "is_candidate": True,
                "confidence": 0.91,
                "mapping_path": "synthesis-agent",
            }
        ],
    },
    "step06": {
        "status": "ok",
        "verified": True,
        "rmc_exit_code": 0,
        "vacuity_status": {"is_vacuous": False},
        "mutation_score": 95.0,
    },
    "step07": {
        "status": "ok",
        "installation_report": [
            {
                "source_path": "/tmp/model.rebeca",
                "dest_path": "/tmp/pkg/model.rebeca",
                "status": "promoted",
            }
        ],
    },
    "step08": {
        "status": "ok",
        "summary_path": "/tmp/reports/Rule-22/summary.json",
        "summary": {"total_rules": 10, "rules_passed": 9, "score_mean": 91.5},
    },
}


MISSING_REQUIRED_FIELD: dict[str, str] = {
    "step01": "source_file_path",
    "step02": "routing",
    "step03": "abstraction_summary",
    "step04": "model_artifact",
    "step05": "candidate_artifacts",
    "step06": "verified",
    "step07": "installation_report",
    "step08": "summary_path",
    "fsm_action": "action",
}


@pytest.mark.parametrize("step_id", sorted(VALID_FIXTURES))
def test_validate_step_output_accepts_valid_fixtures(step_id: str) -> None:
    payload = copy.deepcopy(VALID_FIXTURES[step_id])
    errors = validate_step_output(step_id=step_id, data=payload)
    assert errors == []


@pytest.mark.parametrize("step_id", sorted(VALID_FIXTURES))
def test_validate_step_output_rejects_missing_required_field(step_id: str) -> None:
    payload = copy.deepcopy(VALID_FIXTURES[step_id])
    payload.pop(MISSING_REQUIRED_FIELD[step_id], None)
    errors = validate_step_output(step_id=step_id, data=payload)
    assert errors


def test_assert_step_output_raises_machine_readable_envelope() -> None:
    payload = copy.deepcopy(VALID_FIXTURES["step01"])
    payload.pop("source_file_path", None)
    with pytest.raises(ValueError) as exc_info:
        assert_step_output(step_id="step01", data=payload)
    envelope = json.loads(str(exc_info.value))
    assert envelope["error"] == "step_contract_violation"
    assert envelope["step"] == "step01"
    assert envelope["violations"]


def test_validate_step_output_rejects_non_dict() -> None:
    errors = validate_step_output("step01", [])  # type: ignore[arg-type]
    assert errors


def test_validate_step_output_unknown_step() -> None:
    errors = validate_step_output("step99", {"status": "ok"})
    assert errors
    assert "unknown-step" in errors[0]


def test_step06_requires_vacuity_and_mutation_fields() -> None:
    """FSM transition guard needs vacuity_status.is_vacuous and mutation_score."""
    base = copy.deepcopy(VALID_FIXTURES["step06"])

    missing_vacuity = {k: v for k, v in base.items() if k != "vacuity_status"}
    assert validate_step_output("step06", missing_vacuity)

    missing_mutation = {k: v for k, v in base.items() if k != "mutation_score"}
    assert validate_step_output("step06", missing_mutation)


def test_step05_uses_candidate_artifacts_key() -> None:
    """step05 artifact must use candidate_artifacts[], not the legacy candidates[] key."""
    legacy = {
        "status": "ok",
        "candidates": [{"path": "/tmp/c.property", "confidence": 0.9, "mapping_path": "x"}],
    }
    assert validate_step_output("step05", legacy)


def test_step03_uses_abstraction_summary_nesting() -> None:
    """step03 artifact must nest actor_map/variable_map under abstraction_summary."""
    flat = {"status": "ok", "actors": ["Ship"], "state_variables": ["speed"], "assertion_map": {}}
    assert validate_step_output("step03", flat)
