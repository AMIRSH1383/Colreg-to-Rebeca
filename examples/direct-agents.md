# Binding and synthesis stages

The Rebeca extractor now includes `source_context` per class: original member
text, signatures and line ranges. Existing inventory keys are retained. The v2
binder passes matching source lines as `usage_context` for each candidate, with
explicit shadowing/lexical uncertainty. This helps inspect models without comments
but does not establish undocumented units or semantic equivalence.

Duplicate classes/instances and instances of undeclared classes are rejected.
The synthesis API refuses existing generated artifacts, even when invoked outside
the CLI. Tests after these changes: 62 passed plus 13 subtests. The original
navigation model was extracted into `work/analysis/model-context-inventory.json`.
No new LLM accuracy or RMC-result improvement is claimed by these structural tests.

These implement sections 3 and 4 of `Future work.md`. The previous research's
mapping/synthesis division and targeted property updates are retained. Inputs
are direct COLREG extraction and the actual model inventory, with no intermediate
regulatory translation. Historical model/property assets and results are preserved.

## Files to use

| Stage | Contract | Executable implementation |
| --- | --- | --- |
| Semantic binding / formalization | `agents/semantic_binding_agent.md` | `binding.py`, `evidence_binding.py`, `agent_stages.py` under `scripts/direct_colreg/` |
| Synthesis | `agents/synthesis_agent.md` | `scripts/direct_colreg/synthesis.py` and `agent_stages.py` |
| Separate stage entry point | CLI below | `scripts/direct_agents.py` |
| Integrated pipeline | Existing source-to-RMC command | `scripts/direct_colreg.py` |

The semantic agent uses the configured real LLM with finite model candidates and
source evidence. The synthesis agent is deterministic; another LLM call is not
needed to render validated typed logic. The typed formalization is currently
proposed during COLREG extraction and checked/rendered downstream; binding does
not reinterpret it or prove source equivalence.

## Run the two stages separately

The example uses a saved *actual LLM* extraction from the prior frozen experiment.
This is a stage-integration check, not a fresh source-extraction generalization test.
Use new output directories for repeated runs.

```powershell
$env:PYTHONPATH='D:/Research/research-RebecAI/.experiment-deps'
python scripts/direct_agents.py bind --source examples/rule22a/source.txt --extraction work/milestone3/evaluation-001/rule22a/extraction.json --model examples/rule22a/range-model.rebeca --catalog configs/evidence_model_catalog.json --output work/direct-agents/binding-001
python scripts/direct_agents.py synthesize --source examples/rule22a/source.txt --extraction work/milestone3/evaluation-001/rule22a/extraction.json --model examples/rule22a/range-model.rebeca --binding work/direct-agents/binding-001/binding.json --output work/direct-agents/synthesis-001
```

Add `--property path/to/existing.property` to preserve unrelated properties.
Binding emits `binding.json` plus raw provider artifacts and `usage.json`.
Synthesis emits the unchanged `model.rebeca`, merged `model.property`, witness
properties and `synthesis.json`, including hashes and unsupported requirements.
Existing integrated runs now also emit `binding-handoff.json`.

The CLI validates extraction/source consistency before either stage. The handoff
is tied to exact model and extraction bytes, and actual declarations/types/actors
are rechecked before synthesis. Hash checks establish input identity, not semantic
correctness or protection against deliberate artifact forgery.

## Necessary correctness changes

- Distinct regulatory entities cannot be silently rendered against one actor.
- Binding fields must share the same nonempty actor-instance scope.
- Failed rendering cannot leave a partially generated requirement.
- Missing units/meanings remain unresolved; synthesis cannot invent state or
  constructor values that would make requirements pass.
- Prior research's default comparison and inferred initializations are not reused.
- Temporal, behavioral and cross-actor requirements remain unsupported.

The v2 evidence binder still requires documented scoped meaning and units before
accepting a candidate. This does not provide arbitrary comment-free semantic
inference; undocumented model meaning requires external evidence. No model author
review or physical compliance is implied. All-round color and Annex intensity
remain gaps unless separately established by evidence.

Tests: `python -m pytest tests/test_agent_stages.py tests/test_evidence_binding.py tests/test_direct_colreg.py tests/test_rule22_milestone.py tests/test_run_rmc_execution_interface.py tests/test_extract_rebeca.py tests/test_extractor_evaluation.py -q`.

## Observed integration checks

The focused suite passed 60 tests and 13 subtests. New tests cover same-class
cross-entity rejection, inconsistent instance scopes, handoff identity checks,
fabricated-field rejection and preservation of existing model/property content.

`work/direct-agents/binding-001` records one real configured LLM binding call:
35649 input tokens, 911 output tokens, monetary cost unavailable. Five candidate
selections failed the unchanged 0.9 confidence policy and the color-qualified
all-round concept abstained. `synthesis-001/synthesis.json` therefore correctly
records UNSUPPORTED_SEMANTICS and no generated property. This experiment reuses
the prior actual extraction; no new extraction success is claimed.

`work/direct-agents/archived-binding-synthesis-001` separately checks compatibility
using the prior frozen run's accepted binding decisions, explicitly not new LLM
selections. `compatibility.json` records byte comparison of generated properties
and actual RMC execution/witness results. Historical results are never overwritten.
The generated property was byte-identical to the earlier property. Actual RMC
reported VERIFIED; the independent witness-absence assertion was VIOLATED with
a saved counterexample, establishing reachable applicability for that subset.
