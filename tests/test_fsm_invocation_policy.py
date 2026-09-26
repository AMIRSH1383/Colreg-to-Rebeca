"""Invocation-policy tests: workflow_fsm.py is the canonical coordinator interface.

Guards against workflow_fsm losing its identity as a pure decision engine.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "rebeca_tooling" / "scripts"
AGENTS_DIR = Path(__file__).resolve().parents[1] / "agents"

WORKFLOW_FSM = SCRIPTS / "workflow_fsm.py"
COORDINATOR_MD = AGENTS_DIR / "legata_to_rebeca.md"


# ---------------------------------------------------------------------------
# Module docstrings identify each script's role
# ---------------------------------------------------------------------------

class TestModuleDocstrings:
    def test_workflow_fsm_docstring_identifies_decision_engine(self):
        text = WORKFLOW_FSM.read_text(encoding="utf-8")
        assert "Pure decision engine" in text or "decision engine" in text.lower(), (
            "workflow_fsm.py docstring must identify it as a pure decision engine"
        )

    def test_workflow_fsm_docstring_says_no_side_effects_beyond_fsm_state(self):
        text = WORKFLOW_FSM.read_text(encoding="utf-8")
        assert "fsm_state.json" in text, (
            "workflow_fsm.py docstring must mention the only file it writes (fsm_state.json)"
        )


# ---------------------------------------------------------------------------
# Coordinator doc uses workflow_fsm.py
# ---------------------------------------------------------------------------

class TestCoordinatorDocInvocationPolicy:
    def test_coordinator_references_workflow_fsm(self):
        text = COORDINATOR_MD.read_text(encoding="utf-8")
        assert "workflow_fsm.py" in text, (
            "legata_to_rebeca.md must reference workflow_fsm.py as the FSM interface"
        )

    def test_coordinator_has_invocation_policy_section(self):
        text = COORDINATOR_MD.read_text(encoding="utf-8")
        assert "FSM Invocation Policy" in text, (
            "legata_to_rebeca.md must contain an 'FSM Invocation Policy' section"
        )

    def test_coordinator_policy_identifies_workflow_fsm_as_normative(self):
        text = COORDINATOR_MD.read_text(encoding="utf-8")
        assert "canonical" in text and "workflow_fsm.py" in text, (
            "legata_to_rebeca.md must describe workflow_fsm.py as the canonical interface"
        )

# ---------------------------------------------------------------------------
# Terminal handling — completeness and determinism (Issue 5)
# ---------------------------------------------------------------------------

_TERMINAL_TYPES = {"finish", "block", "skip", "error"}


class TestTerminalHandlingDoc:
    """Terminal handling section must be complete, list-form, and unambiguous."""

    def _section_text(self) -> str:
        full = COORDINATOR_MD.read_text(encoding="utf-8")
        # Extract from "Part 3" header to the next "##" section
        start = full.find("### Part 3")
        end = full.find("\n## ", start)
        return full[start:end] if end != -1 else full[start:]

    def test_all_four_terminal_types_documented(self):
        section = self._section_text()
        for t in _TERMINAL_TYPES:
            assert f"`{t}`" in section, (
                f"Terminal type '{t}' must be documented in Part 3"
            )

    def test_intro_says_loop_ends(self):
        section = self._section_text()
        assert "end" in section.lower() or "loop" in section.lower(), (
            "Part 3 intro must state that terminal actions end the executor loop"
        )

    def test_intro_says_must_not_invoke_step(self):
        section = self._section_text()
        assert "MUST NOT" in section or "must not" in section.lower(), (
            "Part 3 intro must explicitly say terminal actions must not invoke another step"
        )

    def test_terminal_section_uses_list_not_table(self):
        section = self._section_text()
        # A markdown table has lines starting with '|'
        table_lines = [l for l in section.splitlines() if l.strip().startswith("|")]
        assert not table_lines, (
            "Part 3 terminal handling must use list form, not a markdown table"
        )

    def test_finish_surfaces_summary_json(self):
        section = self._section_text()
        assert "summary.json" in section, (
            "finish terminal action must reference summary.json as the output to surface"
        )

    def test_block_surfaces_reason_code(self):
        section = self._section_text()
        assert "reason_code" in section, (
            "block terminal action must reference reason_code"
        )

    def test_skip_surfaces_next_action(self):
        section = self._section_text()
        assert "next_action" in section, (
            "skip terminal action must reference step02 classification.next_action"
        )

    def test_error_says_do_not_retry(self):
        section = self._section_text()
        assert "do not retry" in section.lower() or "not retry" in section.lower(), (
            "error terminal action must say 'do not retry'"
        )

    def test_terminal_types_match_fsm_schema_enum(self):
        """Doc terminal types must be a superset of (or equal to) the schema's type enum."""
        import json
        schema_path = COORDINATOR_MD.parent.parent / "skills" / "rebeca_tooling" / "schemas" / "workflow-fsm-action.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema_terminal = {
            t for t in schema["properties"]["action"]["properties"]["type"]["enum"]
            if t not in ("run_step", "refine_step")
        }
        assert schema_terminal == _TERMINAL_TYPES, (
            f"Doc terminal types {_TERMINAL_TYPES} must match schema terminal types {schema_terminal}"
        )


# ---------------------------------------------------------------------------
# Step Bindings — coverage and anti-drift (Issue 6)
# ---------------------------------------------------------------------------

import json as _json

_SCHEMA_PATH = COORDINATOR_MD.parent.parent / "skills" / "rebeca_tooling" / "schemas" / "workflow-fsm-action.schema.json"
_FSM_SCHEMA = _json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))

# All non-terminal step and agent values from the schema
_SCHEMA_STEPS = {
    s for s in _FSM_SCHEMA["properties"]["action"]["properties"]["step"]["enum"]
    if s != "none"
}
_SCHEMA_AGENTS = {
    a for a in _FSM_SCHEMA["properties"]["action"]["properties"]["agent"]["enum"]
    if a != "none"
}


class TestStepBindings:
    """Step Bindings section must cover every schema step/agent and carry the anti-drift rule."""

    def _bindings_text(self) -> str:
        full = COORDINATOR_MD.read_text(encoding="utf-8")
        start = full.find("## Step Bindings")
        end = full.find("\n## ", start + 1)
        return full[start:end] if end != -1 else full[start:]

    def test_bindings_section_exists(self):
        assert "## Step Bindings" in COORDINATOR_MD.read_text(encoding="utf-8"), (
            "legata_to_rebeca.md must have a 'Step Bindings' section"
        )

    def test_bindings_intro_mentions_action_step_and_agent(self):
        section = self._bindings_text()
        assert "action.step" in section and "action.agent" in section, (
            "Step Bindings intro must reference both action.step and action.agent"
        )

    def test_bindings_intro_has_anti_drift_rule(self):
        section = self._bindings_text()
        assert "do not remap" in section.lower() or "remap" in section.lower(), (
            "Step Bindings intro must include an anti-remap (anti-drift) rule"
        )

    @pytest.mark.parametrize("step", sorted(_SCHEMA_STEPS))
    def test_all_schema_steps_appear_in_bindings(self, step):
        section = self._bindings_text()
        assert step in section, (
            f"Schema step '{step}' must appear in the Step Bindings section"
        )

    @pytest.mark.parametrize("agent", sorted(_SCHEMA_AGENTS))
    def test_all_schema_agents_appear_in_bindings(self, agent):
        section = self._bindings_text()
        assert agent in section, (
            f"Schema agent '{agent}' must appear in the Step Bindings section"
        )

    def test_bindings_uses_list_not_table(self):
        section = self._bindings_text()
        table_lines = [l for l in section.splitlines() if l.strip().startswith("|")]
        assert not table_lines, (
            "Step Bindings must use list form, not a markdown table"
        )

    def test_binding_count_matches_schema_step_count(self):
        section = self._bindings_text()
        bullet_lines = [l for l in section.splitlines() if l.strip().startswith("- `step")]
        assert len(bullet_lines) == len(_SCHEMA_STEPS), (
            f"Expected {len(_SCHEMA_STEPS)} binding bullets, found {len(bullet_lines)}"
        )


# ---------------------------------------------------------------------------
# Enum-to-artifact mapping consistency (Issue 7)
# ---------------------------------------------------------------------------

def _import_from_scripts(name: str):
    """Import a module from SCRIPTS dir, registering it in sys.modules."""
    import importlib
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    sys.modules.pop(name, None)
    return importlib.import_module(name)


class TestEnumToArtifactMapping:
    """workflow_fsm and output_policy must agree on enum→artifact mapping."""

    def test_workflow_fsm_pipeline_artifacts_in_output_policy_allowed_set(self):
        fsm = _import_from_scripts("workflow_fsm")
        op = _import_from_scripts("output_policy")
        import inspect, ast as _ast
        src = inspect.getsource(op.step_artifact_path)
        tree = _ast.parse(src)
        allowed: set[str] = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Set):
                for elt in node.elts:
                    if isinstance(elt, _ast.Constant) and isinstance(elt.s, str):
                        allowed.add(elt.s)
        fsm_artifacts = {step.artifact for step in fsm._PIPELINE}
        unknown = fsm_artifacts - allowed
        assert not unknown, (
            f"workflow_fsm._PIPELINE artifacts not in output_policy allowed set: {unknown}"
        )

    def test_known_enum_artifact_divergences_are_intentional(self):
        """Document the three intentional enum≠artifact cases and catch unexpected ones."""
        fsm = _import_from_scripts("workflow_fsm")
        expected_divergences = {
            "step05_synthesis": "step04_synthesis",
            "step07_packaging": "step06_packaging_manifest",
        }
        actual_divergences = {
            step.step_enum: step.artifact
            for step in fsm._PIPELINE
            if step.step_enum != step.artifact
        }
        assert actual_divergences == expected_divergences, (
            f"Unexpected enum↔artifact divergences detected.\n"
            f"  Expected: {expected_divergences}\n"
            f"  Actual:   {actual_divergences}\n"
            "Update this test and the coordinator doc if a new intentional divergence is added."
        )

    def test_coordinator_doc_lists_artifact_names_not_enums_for_divergent_steps(self):
        """The doc mapping section must use artifact names (step04_synthesis, not step05_synthesis)."""
        text = COORDINATOR_MD.read_text(encoding="utf-8")
        assert "step04_synthesis" in text, (
            "Coordinator doc must list artifact name 'step04_synthesis', not enum 'step05_synthesis'"
        )
        assert "step06_packaging_manifest" in text, (
            "Coordinator doc must list artifact name 'step06_packaging_manifest', not enum 'step07_packaging'"
        )

    def test_coordinator_doc_explains_enum_artifact_divergence(self):
        text = COORDINATOR_MD.read_text(encoding="utf-8")
        assert "enum" in text.lower() and ("differ" in text.lower() or "≠" in text or "artifact name" in text.lower()), (
            "Coordinator doc must explain that action.step enum and artifact name can differ"
        )

    def test_coordinator_doc_does_not_use_raw_action_step_placeholder(self):
        text = COORDINATOR_MD.read_text(encoding="utf-8")
        assert "--step <action.step>" not in text, (
            "Coordinator execution loop must not pass raw action.step directly to artifact_writer"
        )

    def test_coordinator_doc_uses_artifact_name_placeholder(self):
        text = COORDINATOR_MD.read_text(encoding="utf-8")
        assert "--step <artifact_step_name_for_action_step>" in text, (
            "Coordinator execution loop must show artifact-name mapping placeholder for artifact_writer --step"
        )

    def test_coordinator_doc_has_anti_drift_note(self):
        text = COORDINATOR_MD.read_text(encoding="utf-8")
        start = text.find("## Canonical Artifact Persistence")
        section = text[start:text.find("\n## ", start + 1)]
        assert "workflow_fsm" in section and "output_policy" in section, (
            "Canonical Artifact Persistence must name workflow_fsm and output_policy in the anti-drift note"
        )
