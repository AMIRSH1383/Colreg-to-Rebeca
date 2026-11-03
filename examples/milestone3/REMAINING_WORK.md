# Milestone 3 completion boundaries

The implementation and available-model evaluation are complete. Full Rule 22(a)
verification remains blocked by missing model semantics, not by a missing mapping
override. Source audit, catalog, finite evidence-based LLM matching, deterministic
validation, independent binding tests and frozen real extraction/RMC execution
are documented in README.md and work/milestone3/RESULTS.md.

## Remaining evidence requirements

| Gap | Evidence needed | Smallest justified future change |
| --- | --- | --- |
| Colored all-round light scope | Model-owner documentation establishing whether the configured range applies to each prescribed color, and under what installation assumptions | Add cited model documentation to a separately versioned model/catalog; bind only after independent review. Merely repeating the regulation is not model evidence. |
| Annex I Section 8 intensity | A physical intensity/visibility relation, inputs, units, assumptions and applicability, independently reviewed against the Annex | Separate photometric extension and validation; range comparisons cannot establish intensity compliance. |
| Navigation units and semantics | Consistent geometry/time/unit definitions and documented meanings of light settings | Resolve unit/scaling contradictions in a separate model revision, then regenerate the hash-bound catalog. Do not infer nautical miles from constructor values. |
| Navigation compilation | Independently justified numeric conversion semantics at the recorded compiler errors | Separate model repair with regression checks; no edits were made for this milestone. |
| Semantic correctness review | Independent reviewer assessment of extraction, scope and each accepted mapping | Record actual reviewer provenance and decisions; analyst annotations and LLM confidence are not human review. |

No model extension is implemented here. These are proposals requiring evidence;
inventing units, colors or photometric equations would defeat the binding audit.

## Additional independent checker evaluation

`scripts/evaluate_milestone3_boundaries.py` checks the saved frozen subset without
new LLM requests. It varies lengths 49/50/51 and independently reduces each range
below its requirement. It also checks applicability independently at each length.
The oracle is evaluation code and never becomes extraction or mapping input.

The all-round mutation is deliberately retained as an uncovered case. A satisfied
generated property at lengths 50 or 51 in that case demonstrates an omission,
not successful regulatory verification. Whole-rule coverage remains incomplete.

```powershell
python scripts/evaluate_milestone3_boundaries.py --run work/milestone3/evaluation-001/rule22a --output work/milestone3/boundaries-new --jar D:/Research/research-RebecAI/output/experiments/toolchain/rmc.jar --wsl Ubuntu --timeout 30
```

Use a fresh output directory. Each checker stage has bounded execution; failures,
timeouts, XML results and counterexamples are saved. Three isolated jobs may run
concurrently. No prior experiment output or original model is overwritten.
