"""Rigorous tests for the fsm_action JSON schema (conditional logic) and
schema-reference alignment between the coordinator doc, the JSON schema file,
and the step_schemas.py in-process definition."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest
from jsonschema import validate
from jsonschema.exceptions import ValidationError

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "rebeca_tooling" / "scripts"
SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "skills" / "rebeca_tooling" / "schemas"
COORDINATOR_MD = Path(__file__).resolve().parents[1] / "agents" / "legata_to_rebeca.md"

sys.path.insert(0, str(SCRIPTS))

# Load the schema directly from the file to ensure we are testing the actual deliverable.
SCHEMA_PATH = Path("skills/rebeca_tooling/schemas/workflow-fsm-action.schema.json")
with SCHEMA_PATH.open("r", encoding="utf-8") as f:
    FSM_SCHEMA = json.load(f)

VALID_REFINE_STEP = {
    "status": "retry",
    "current_state": "abstracted",
    "next_state": "abstracted",
    "action": {
        "type": "refine_step",
        "step": "step02_abstraction",
        "agent": "abstraction_agent",
        "inputs": {
            "rule_id": "Rule-22",
            "prior_artifact_path": "output/work/Rule-22/step02_abstraction.json",
            "issue_class": "missing_actors",
            "issue_detail": "LLM failed to extract OwnShip",
            "attempt_index": 2,
            "budget_remaining": 1
        }
    },
    "reason_code": "abstraction_incomplete",
    "required_artifacts": ["step02_abstraction.json"],
    "missing_artifacts": []
}

VALID_FINISH = {
    "status": "ok",
    "current_state": "reported",
    "next_state": "none",
    "action": {
        "type": "finish",
        "step": "none",
        "agent": "none",
        "inputs": {}
    },
    "reason_code": "pipeline_complete",
    "required_artifacts": ["step07_reporting.json"],
    "missing_artifacts": []
}

def test_valid_refine_step():
    validate(instance=VALID_REFINE_STEP, schema=FSM_SCHEMA)

def test_valid_finish():
    validate(instance=VALID_FINISH, schema=FSM_SCHEMA)

def test_refine_step_missing_inputs():
    """If action.type is refine_step, specific inputs are required."""
    invalid = copy.deepcopy(VALID_REFINE_STEP)
    # Remove one required refinement field
    invalid["action"]["inputs"].pop("issue_class")

    with pytest.raises(ValidationError) as exc_info:
        validate(instance=invalid, schema=FSM_SCHEMA)
    assert "'issue_class' is a required property" in str(exc_info.value)

def test_finish_requires_none_step_agent():
    """If action.type is finish, step and agent MUST be 'none'."""
    invalid = copy.deepcopy(VALID_FINISH)
    invalid["action"]["step"] = "step07_reporting"

    with pytest.raises(ValidationError) as exc_info:
        validate(instance=invalid, schema=FSM_SCHEMA)
    assert "'none' was expected" in str(exc_info.value)

def test_invalid_action_type():
    invalid = copy.deepcopy(VALID_RUN_STEP)
    invalid["action"]["type"] = "invalid_type"
    with pytest.raises(ValidationError):
        validate(instance=invalid, schema=FSM_SCHEMA)

def test_mismatched_enums():
    invalid = copy.deepcopy(VALID_RUN_STEP)
    invalid["action"]["step"] = "wrong_step_name"
    with pytest.raises(ValidationError):
        validate(instance=invalid, schema=FSM_SCHEMA)


# ---------------------------------------------------------------------------
# Schema-reference alignment: doc pointers must resolve to real artifacts
# ---------------------------------------------------------------------------

class TestSchemaReferenceAlignment:
    """Coordinator doc references must resolve to actual, correct schema artifacts."""

    def test_workflow_fsm_action_schema_file_exists(self):
        path = SCHEMAS_DIR / "workflow-fsm-action.schema.json"
        assert path.exists(), (
            f"Schema file referenced in coordinator doc not found: {path}"
        )

    def test_step_schemas_py_exists(self):
        path = SCRIPTS / "step_schemas.py"
        assert path.exists(), (
            f"step_schemas.py referenced in coordinator doc not found: {path}"
        )

    def test_step_schemas_has_fsm_action_key(self):
        from step_schemas import STEP_OUTPUT_SCHEMAS as _SCHEMAS  # noqa: PLC0415
        assert "fsm_action" in _SCHEMAS, (
            "step_schemas.py must define an 'fsm_action' key"
        )

    def test_coordinator_doc_references_schema_file(self):
        text = COORDINATOR_MD.read_text(encoding="utf-8")
        assert "workflow-fsm-action.schema.json" in text, (
            "legata_to_rebeca.md must reference workflow-fsm-action.schema.json"
        )

    def test_coordinator_doc_references_step_schemas_fsm_action(self):
        text = COORDINATOR_MD.read_text(encoding="utf-8")
        assert "step_schemas.py" in text and "fsm_action" in text, (
            "legata_to_rebeca.md must reference step_schemas.py and the 'fsm_action' key"
        )

    def test_coordinator_doc_mentions_terminal_none_contract(self):
        text = COORDINATOR_MD.read_text(encoding="utf-8")
        assert 'step = "none"' in text or "step=\u201cnone\u201d" in text or 'step = \'none\'' in text or '"none"' in text, (
            "legata_to_rebeca.md must document that terminal actions use step/agent = 'none'"
        )

    def test_action_type_enum_matches_between_schema_and_step_schemas(self):
        """JSON schema file and step_schemas.py must agree on action.type enum values."""
        from step_schemas import STEP_OUTPUT_SCHEMAS as _SCHEMAS  # noqa: PLC0415
        json_schema_types = set(FSM_SCHEMA["properties"]["action"]["properties"]["type"]["enum"])
        py_schema_types = set(
            _SCHEMAS["fsm_action"]["properties"]["action"]["properties"]["type"]["enum"]
        )
        assert json_schema_types == py_schema_types, (
            f"action.type enum mismatch — JSON schema: {json_schema_types}, "
            f"step_schemas.py: {py_schema_types}"
        )

    def test_action_step_enum_matches_between_schema_and_step_schemas(self):
        from step_schemas import STEP_OUTPUT_SCHEMAS as _SCHEMAS  # noqa: PLC0415
        json_steps = set(FSM_SCHEMA["properties"]["action"]["properties"]["step"]["enum"])
        py_steps = set(
            _SCHEMAS["fsm_action"]["properties"]["action"]["properties"]["step"]["enum"]
        )
        assert json_steps == py_steps, (
            f"action.step enum mismatch — JSON schema: {json_steps}, "
            f"step_schemas.py: {py_steps}"
        )

    def test_action_agent_enum_matches_between_schema_and_step_schemas(self):
        from step_schemas import STEP_OUTPUT_SCHEMAS as _SCHEMAS  # noqa: PLC0415
        json_agents = set(FSM_SCHEMA["properties"]["action"]["properties"]["agent"]["enum"])
        py_agents = set(
            _SCHEMAS["fsm_action"]["properties"]["action"]["properties"]["agent"]["enum"]
        )
        assert json_agents == py_agents, (
            f"action.agent enum mismatch — JSON schema: {json_agents}, "
            f"step_schemas.py: {py_agents}"
        )

    def test_terminal_actions_require_none_step_in_json_schema(self):
        """Schema allOf rule: finish/block/skip must have step='none'."""
        for action_type in ("finish", "block", "skip"):
            invalid = {
                "status": "ok",
                "current_state": "reported",
                "next_state": "none",
                "action": {
                    "type": action_type,
                    "step": "step07_reporting",  # wrong — should be "none"
                    "agent": "none",
                    "inputs": {},
                },
                "reason_code": "pipeline_complete",
                "required_artifacts": [],
                "missing_artifacts": [],
            }
            with pytest.raises(ValidationError, match="none"):
                validate(instance=invalid, schema=FSM_SCHEMA)

    def test_terminal_actions_require_none_step_in_step_schemas(self):
        """In-process schema allOf rule mirrors the JSON schema."""
        from step_schemas import validate_step_output  # noqa: PLC0415
        for action_type in ("finish", "block", "skip"):
            payload = {
                "status": "ok",
                "current_state": "reported",
                "next_state": "none",
                "action": {
                    "type": action_type,
                    "step": "step07_reporting",  # wrong
                    "agent": "none",
                    "inputs": {},
                },
                "reason_code": "pipeline_complete",
                "required_artifacts": [],
                "missing_artifacts": [],
            }
            errors = validate_step_output("fsm_action", payload)
            assert errors, (
                f"step_schemas validate_step_output must flag step != 'none' "
                f"for terminal type '{action_type}'"
            )
