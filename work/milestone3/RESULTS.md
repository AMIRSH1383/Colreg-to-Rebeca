# Milestone 3 — evidence-based binding results

**The frozen run improves binding from complete abstention to five of six
measurement concepts, but does not establish complete Rule 22(a) compliance.**
Four range obligations are generated and actually verified in the isolated model.
All-round color scope and Annex intensity remain unresolved. Navigation-model
semantics are not silently repaired or declared verified.

## Source audit

`configs/evidence_model_catalog.json` inventories all 58 state fields across
`work/Original Model.rebeca` and `examples/rule22a/range-model.rebeca`.
`examples/milestone3/model-audit.md` renders ownership, declarations, constructor
writes, subsequent writes, reads, state category, physical units, meanings,
suitability, uncertainty and exact source evidence. Lexical evidence is not a
proof of reachability or a complete compiler/data-flow analysis.

`configs/model_evidence_annotations.json` contains source-cited analyst notes.
No human review is claimed. No regulatory translation, historical property,
expected extraction JSON or rule-specific mapping table is used.

Material navigation-model findings:

- Length is divided by 100 in geometry but used unscaled in another distance
  calculation. Raw12/10 constructor arguments are not established metre lengths.
- Light ranges are constructor-only settings without operational reads, updates,
  physical-unit declarations or photometric calculations.
- Signal-light and all-round-light ranges are distinct fields; no equivalence is
  established between them.
- Engine-on is constant configuration, not demonstrated readiness.
- The abstract ship_velocity field does not drive the motion timing path.
- Simulated scan coordinates, visibility settings and legal applicability are not
  interchangeable.
- Proximity comparison direction and direction/velocity array indexing contain
  inconsistencies documented with source references.

The isolated fixture's pre-existing header explicitly supplies metres and
nautical-mile visibility-range units. That documentation plus declarations and
constructor evidence supports configured-attribute checks, not measured physical
performance or installation/color/intensity compliance.

## Implementation

- `scripts/direct_colreg/model_evidence.py`: audit, source/hash/quotation validation
  and v2 catalog construction.
- `scripts/audit_model_semantics.py`: reproducible catalog CLI.
- `scripts/render_model_audit.py`: readable audit renderer.
- `scripts/direct_colreg/evidence_binding.py`: source-evidenced candidate filtering,
  bounded real LLM selection and deterministic validation.
- `scripts/direct_colreg/binding.py`: v2 dispatch; v1 retained for old regressions.
- `tests/test_evidence_binding.py`: independent synthetic safety/regression tests.
- `scripts/evaluate_evidence_binding.py`: frozen real-inference evaluation.
- `scripts/check_bound_property.py`: isolated negative checker test of saved property.
- `examples/milestone3/README.md`: exact reproduction commands and limits.

The confidence cutoff remains 0.9. A selected field needs actual ownership/type,
source-supported units, noncontradictory scoped meaning, exact source citations
and declaration/documentary support. Indistinguishable descriptions cannot be
disambiguated using initializer values. Missing evidence causes abstention.
Selections remain labeled LLM-assisted and not human reviewed.

## Frozen actual-inference tests

Evidence: `work/milestone3/evaluation-001/summary.json` and its `freeze/` snapshot.
Frozen implementation, prompt, schema, source, catalog and annotation hashes
remained unchanged between tests and the final Rule22(a) run. Current source
fingerprints were also checked against the snapshot after completion.

| Binding-only test | Actual result | Expected outcome matched? |
| --- | --- | --- |
| Positive with nonsemantic variable name q | Selected q using documentary evidence | Yes |
| Missing ocean-depth meaning | Abstained | Yes |
| Two indistinguishable documented fields | Abstained | Yes |
| Renamed variable with retained documentary meaning | Selected renamed_span | Yes |

These are four real LLM calls on independent synthetic model evidence. Mocked
unit-test responses are separate and do not count as actual inference results.

## Fresh Rule22(a) run

Evidence: `work/milestone3/evaluation-001/rule22a/`.

- Actual LLM semantic extraction completed and validated against source/schema.
- Five bindings accepted with source citations: length, masthead, side, stern and
  towing configured-range attributes. No catalog alias answer table was supplied.
- All-round binding abstained because white/red/green/yellow applicability is not
  established in model documentation; confidence was not lowered or overridden.
- Four generated obligations passed actual RMC verification.
- The independent negated applicability assertion failed with a saved
  counterexample: the condition is reachable, so this satisfaction is non-vacuous.
- Supported subset: VERIFIED. Whole-source status: UNSUPPORTED_SEMANTICS.
- Full-source verification remains false; independent semantic review is pending.

Actual positive XML: `rule22a/verification/result.xml`.
Applicability witness XML: `rule22a/applicability-0/result.xml` and
`result.counterexample.xml`. Detailed mappings and evidence IDs: `bindings.json`.
Generated property: `model.property`.

The development probe resolved all six measurements; that more permissive
stochastic outcome is preserved as development evidence, not substituted for the
conservative frozen result. No missing color semantics were inserted afterward.

## Negative checker evidence

`work/milestone3/negative-rmc-001/report.json` records an isolated copy whose
masthead setting changes from 6 to 5 while the frozen generated property stays
unchanged. Actual RMC returned assertion failed (VIOLATED), with a saved trace.
The negative test passed even though the executable exit code was 0: classification
comes from the actual XML. Neither the input research model nor the frozen model
was changed.

## Tests and remaining limitations

The focused suite passed **57 tests plus 13 subtests**, including all 49 previously
passing Milestone1/2 focused tests. Evidence: `work/milestone3/tests.txt`.
The full historical repository suite was not run.

The frozen evaluation used six real LLM invocations: four binding tests plus
fresh extraction and binding. Reported totals: 117705 input tokens and 2662 output
tokens; usage was available for all six. Monetary cost remains unknown. This
milestone prioritizes correctness rather than inference efficiency.

The navigation evidence gate selected zero unsupported fields. Its unresolved
units, physical semantics and existing compiler issues remain blockers. The
navigation model and Milestone1/2 results were not modified.

Remaining limits: bounded lexical audit, unreviewed analyst annotations, uncalibrated
LLM confidence, no automatic proof of semantic equivalence, no physical photometry,
unresolved color/intensity semantics, and no full navigation-model verification.
No JEV is integrated and no arbitrary COLREG coverage is claimed.

## Completion follow-up: boundary and coverage checks

Added `scripts/evaluate_milestone3_boundaries.py`, an independent evaluation oracle
for the saved frozen properties. Generic extraction, binding, prompts, catalog,
renderer and verification code were unchanged; no new LLM calls were needed.
The original frozen real extraction remains the provenance of these properties.

Actual evidence: `work/milestone3/boundaries-001/summary.json` and per-case
`verification/result.xml`, execution logs and counterexample files.

- 18 obligation executions: lengths 49/50/51, each with compliant settings and
  each of five ranges independently reduced below its required value.
- Three independent applicability executions: unreachable at 49, reachable at
  50 and 51. Satisfied implications at 49 are explicitly VACUOUS.
- All eight covered violations at lengths 50/51 were VIOLATED with actual traces.
- All-round mutations remain uncovered: at 50/51 the generated subset still
  satisfies despite the deliberately insufficient all-round setting. These are
  coverage failures, not evidence of whole-rule compliance.
- 21/21 checker outcomes matched the independent expected *subset* behavior.
  Three all-round mutations are explicitly labeled uncovered.
- Checker suite wall time: 66.915 seconds using three isolated concurrent jobs.
  Individual execution times are retained; concurrent totals are not wall time.
- Frozen implementation/property fingerprints unchanged. Original navigation
  and fixture byte hashes were reconfirmed unchanged.

Reachability classifications were appended after execution using the saved actual
witness verdicts; no verification outcomes were replaced or simulated. The current
harness includes this classification for reproduction. Regression rerun: 57 tests
and 13 subtests passed in 0.54 seconds. `git diff --check` passed.

`examples/milestone3/REMAINING_WORK.md` describes evidence requirements and separate
model-extension proposals. Available-model implementation and tests are complete;
full Rule22(a) verification remains blocked on color scope, photometry and
independent semantic review. Full navigation verification additionally requires
unit/semantic clarification and separately justified compiler repairs.
