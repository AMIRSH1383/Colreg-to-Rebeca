"""Parity tests ensuring the embedded fsm_action schema matches the JSON schema file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import validate
from jsonschema.exceptions import ValidationError

from skills.rebeca_tooling.scripts.step_schemas import validate_step_output

SCHEMA_PATH = Path("skills/rebeca_tooling/schemas/workflow-fsm-action.schema.json")
with SCHEMA_PATH.open("r", encoding="utf-8") as f:
    JSON_SCHEMA = json.load(f)

# Representative valid/invalid payloads
PAYLOADS = [
    # 1: Valid refine_step
    {
        "status": "retry",
        "current_state": "abstracted",
        "next_state": "abstracted",
        "action": {
            "type": "refine_step",
            "step": "step02_abstraction",
            "agent": "abstraction_agent",
            "inputs": {
                "prior_artifact_path": "path/to/art.json",
                "issue_class": "logic_error",
                "issue_detail": "extraction failed",
                "attempt_index": 2,
                "budget_remaining": 1
            }
        },
        "reason_code": "fix_logic",
        "required_artifacts": ["step02_abstraction.json"],
        "missing_artifacts": []
    },
    # 2: Invalid status
    {
        "status": "invalid_status",
        "current_state": "x",
        "next_state": "y",
        "action": {"type": "run_step", "step": "step01_init", "agent": "init_exec", "inputs": {}},
        "reason_code": "z",
        "required_artifacts": [],
        "missing_artifacts": []
    },
    # 3: Invalid step enum
    {
        "status": "ok",
        "current_state": "x",
        "next_state": "y",
        "action": {"type": "run_step", "step": "invalid_step", "agent": "init_exec", "inputs": {}},
        "reason_code": "z",
        "required_artifacts": [],
        "missing_artifacts": []
    },
    # 4: Missing required refinement field (conditional logic test)
    {
        "status": "retry",
        "current_state": "x",
        "next_state": "x",
        "action": {
            "type": "refine_step",
            "step": "step02_abstraction",
            "agent": "abstraction_agent",
            "inputs": {
                "prior_artifact_path": "path/to/art.json",
                "issue_class": "logic_error",
                # missing issue_detail
                "attempt_index": 2,
                "budget_remaining": 1
            }
        },
        "reason_code": "z",
        "required_artifacts": [],
        "missing_artifacts": []
    },
    # 5: Valid finish
    {
        "status": "ok",
        "current_state": "reported",
        "next_state": "none",
        "action": {
            "type": "finish",
            "step": "none",
            "agent": "none",
            "inputs": {}
        },
        "reason_code": "done",
        "required_artifacts": [],
        "missing_artifacts": []
    },
    # 6: Invalid finish (wrong step)
    {
        "status": "ok",
        "current_state": "reported",
        "next_state": "none",
        "action": {
            "type": "finish",
            "step": "step07_reporting",
            "agent": "none",
            "inputs": {}
        },
        "reason_code": "done",
        "required_artifacts": [],
        "missing_artifacts": []
    }
]

@pytest.mark.parametrize("payload", PAYLOADS)
def test_validation_parity(payload):
    """
    Ensure validate_step_output results match jsonschema.validate results.
    This proves that the embedded schema in step_schemas.py is functionally
    equivalent to the external JSON schema for these key constraints.
    """
    # 1. Run against ground-truth JSON schema
    json_valid = True
    try:
        validate(instance=payload, schema=JSON_SCHEMA)
    except ValidationError:
        json_valid = False

    # 2. Run against embedded schema via helper
    errors = validate_step_output("fsm_action", payload)
    helper_valid = (len(errors) == 0)

    # 3. Assert they agree on validity
    assert helper_valid == json_valid, f"Parity mismatch for payload: {payload}\nHelper errors: {errors}"
