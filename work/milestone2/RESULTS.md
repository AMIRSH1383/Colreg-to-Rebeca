# Milestone 2: critical implementation and evaluation report

**Milestone acceptance is not established.** The generic implementation invokes a
real LLM and a genuinely new synthetic state rule was processed without rule-specific
code changes. However, the frozen Rule22(a) runs abstained at semantic binding,
Rule22(b)'s source is pending, and independent semantic review is incomplete.

## Implemented

- Production entry point: `scripts/direct_colreg.py`.
- Actual authenticated provider: `scripts/direct_colreg/provider.py`, configured
  through `configs/direct_provider.json`. No extraction replay/canned backend.
- General v2 schema and source validator: `schemas/colreg-semantic.schema.json`,
  `scripts/direct_colreg/semantics.py`. Existing extraction prompt/schema reused.
- Candidate filtering and bounded LLM binding: `scripts/direct_colreg/binding.py`.
- Versioned, hash-bound model metadata: `configs/direct_model_catalog.json`.
  It contains units, no concept-to-field answer mappings or rule thresholds.
- Typed logic and deterministic rendering: `scripts/direct_colreg/logic.py`.
- Preserving property insertion: `scripts/direct_colreg/property_io.py`.
- Actual checker execution using existing backend: `scripts/direct_colreg/verification.py`.
- Frozen comparison harness: `scripts/evaluate_direct_colreg.py`.
- Readable report generation: `scripts/report_direct_evaluation.py`.
- Independent checks of saved generated properties: `scripts/evaluate_saved_properties.py`.
- Actual synthetic renderer/backend checks: `scripts/check_state_logic_rmc.py`.
- Tests: `tests/test_direct_colreg.py`; all Milestone1 focused tests retained.
- Exact reproduction instructions: `examples/milestone2/README.md`.

No individual regulation is interpreted through fixed thresholds or named light
categories in production code. Rule-specific expectations exist only in the
independent evaluator and historical Milestone1 regression runner.

## Frozen cohorts

`work/milestone2/evaluation-001/freeze/manifest.json` and
`work/milestone2/evaluation-002/freeze/manifest.json` record Git HEAD, tracked diff,
hashes and source snapshots including untracked implementation. Both cohorts
reported unchanged implementation/prompt/catalog/model hashes between rules.

After cohort1 finished, a provider transport-schema compatibility fix and correction
of an overstrong source-verification report flag were made. No semantic prompts,
model mappings or property templates were tuned on unseen-rule outputs. Cohort2
then froze the revised implementation before running its cases.

| Cohort2 case | Actual result |
| --- | --- |
| Rule22(a) | Real extraction and source/schema validation passed; binding abstained; no property or checker verdict fabricated |
| Rule22(a), whitespace/punctuation | Real extraction validated; binding abstained |
| Rule22(a), paraphrase | Real extraction validated; binding abstained |
| Ambiguous synthetic safe-speed clause | Explicit unsupported semantics; no invented numerical threshold |
| Missing-model battery-temperature concept | Unresolved binding; no fabricated field |
| New synthetic interval/exception clause | Real extraction and two LLM-assisted bindings; actual RMC VERIFIED, applicability reachable |
| Rule19(a-e) | Real extraction validated; eleven requirements explicitly unsupported due to operational, temporal, relational or subjective semantics |
| Rule22(b) | SOURCE_BLOCKED_PENDING_USER; USCG returned HTTP403; user will provide authoritative text |

Rule19 text is attributed to UK MCA's MGN369, sections5.1.1–5.1.5, in
`examples/milestone2/provenance.json`. Synthetic clauses are not actual regulations.
No full navigation-model verification is claimed; evaluation models are isolated.

The main blocker is missing independently established model semantics. Names and
compatible units did not establish equivalence for the frozen binder. The catalog
does not manufacture those equivalences. Conservative abstention is correct, but
it means Rule22(a)'s frozen end-to-end acceptance condition was not met.

The synthetic success is evidence that interval/exception logic can be processed
without rule-specific Python, not evidence of arbitrary COLREG coverage. Its
semantic fidelity and LLM-assisted mappings still require independent review.

## Actual verification evidence separate from frozen failures

The development run at `work/milestone2/development-pipeline-001` performed real
LLM extraction and binding and verified the generated range subset. Annex intensity
remained unsupported. It is exploratory evidence, not a replacement for the failed
frozen Rule22(a) runs.

`work/milestone2/development-boundaries-001` independently evaluates that saved,
actually LLM-generated property at lengths 49/50/51 with individual range faults.
It does not replay extraction JSON into production. Its report must be read for
the individual evidence: **18/18 independent property checks and 18/18 actual RMC
verdicts matched expectations**, including ten intended violations. Applicability
checks were executed separately. This evidence remains labeled development-artifact
verification, not a fresh frozen-cohort extraction.

`work/milestone2/renderer-rmc-001/report.json` records three passing actual RMC
renderer/backend cases (six checker executions including applicability): a
satisfied prohibition, a violation, and an exception causing unreachable
applicability. These are synthetic logic tests, not LLM extraction tests.

## Inference cost and timing

| Cohort | CLI invocations | Reported input tokens | Reported output tokens | Inference wall seconds | Usage complete |
| --- | --- | --- | --- | --- | --- |
| evaluation-001 | 10 | 162564 | 8423 | 185.744 | No: Rule19 provider failure lacks usage |
| evaluation-002 | 11 | 199859 | 16221 | 301.744 | Yes |

These are CLI invocation counts, not guaranteed underlying request counts. Raw
events include transport reconnection behavior. Token totals include CLI context
overhead. Monetary cost is **unknown**, not zero, because subscription billing
and applicable monetary prices are unavailable. Development calls and failed
probes are retained separately and are not hidden inside the cohort totals.
Per-checker runtime is recorded in execution.json; inference runtime is separate.

## Tests and remaining limitations

The focused suite passed **49 tests and thirteen subtests**, including all 34
previous Milestone1 focused tests. See `work/milestone2/tests.txt` and the exact
command in the milestone README. The full historical repository suite was not run.

Supported logic: scalar comparisons, AND/OR/NOT/implication, multiple applicability
conditions, explicit exceptions and simple state obligations/prohibitions.
Temporal and multi-entity relations are not supported. Unit conversion and full
Rebeca grammar analysis are not implemented. LLM scores are not calibrated and
cannot substitute for semantic review. Annex intensity and original-model type
errors remain unresolved. Source-grounding and JSON validation do not prove that
the regulation was completely or correctly interpreted.

Next steps require authoritative Rule22(b) text and independent model-semantic
documentation/review. Add reviewed model evidence before a new freeze, not hidden
test answers. Preserve current failures when comparing any subsequent revision.
