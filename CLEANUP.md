# Completed repository cleanup

Starting revision: `cd5e5d4e844013e4031a3d0291dbdc76d93f2864`.
Branch: `cleanup/colreg-migration`. Changes are local and uncommitted; no push or
publication was performed.

## Migration

- Moved the original model and supplied COLREG excerpts to `inputs/` unchanged.
- Preserved all six historical Legata baselines under `archive/rebecai/`, with
  COLREG versus Istanbul Strait provenance documented. Archived old coordinator,
  FSM, installer/acceptance/reporting tests, transformation utilities, README,
  skill documentation, and the original verification schema.
- Copied the original Rule 19/22 experiment outputs, metadata, reviews and relevant
  logs into `experiments/` without rewriting historical paths or results.
- Kept `agents/colreg_extractor.md` and its schema byte-for-byte unchanged; added a
  portable OpenCode synchronization/check command instead of independently edited
  copies. Retained LICENSE and upstream RebecAI attribution.
- Removed the unreferenced local Windows-path validator; moved and corrected the
  heuristic syntax CLI. Excluded archives from default pytest discovery.
- Retained verification modules in their existing location. Corrected imports,
  JAR discovery, temporary-directory handling, schemas, artifact writes and docs.
  The old verification schema path remains a relative reference to the canonical
  new schema; consumers must resolve relative schema references from its file URI.

## Correctness fixes

Semantic satisfaction now requires an exported result, never compilation or process
exit alone. The gate distinguishes violation, unknown, compile/execution failure,
and disabled/not-run/unknown optional checks. Stale generated C++ and result files
cannot supply evidence for a new failed run. Unknown vacuity results no longer fall
back to a success-like verdict. Negation preserves the whole assertion expression.
Mutation artifacts now match their writer's contract; real mutation tests no longer
simulate a kill. Inconsistent tests were repaired with a bounded cyclic model and
adequate message-queue capacity, without touching the reference research model.

## Validation

- Full active suite: **176 passed, 0 failed, 0 skipped** (163 unit, 13 real-toolchain).
- Strict mypy and flake8: passed.
- Real RMC tests include satisfied/violated properties, parse failures, mutation
  execution and vacuity diagnostics. Violated properties compile but cannot pass.
- Regressions cover unknown results, runtime failure, missing/stale result evidence,
  optional-check uncertainty, imports, extraction schemas and preservation hashes.
- Gate CLI stdout JSON, output schema and fresh canonical artifact: passed.
- Handbook model/property pair: RMC generation, compilation and execution passed.
- OpenCode copy synchronization, leakage scan and `git diff --check`: passed.
- JAR 2.14 SHA-256 matches `configs/rmc_defaults.json`.

Evidence: `experiments/cleanup-validation/`. Earlier failed diagnostic runs were
resolved; final test results above refer to the completed suite.

## Remaining limits and next-stage readiness

The original full model was **NOT RUN** through complete verification: no dedicated
reference property file was present. Its exact bytes are preserved and it is ready
as the input for a deterministic Python Rebeca Extractor. That extractor, binding,
synthesis and reporting remain unimplemented. No new extraction LLM calls were made.

Vacuity remains the documented legacy negated-expression comparison heuristic,
not a general proof of logical antecedent reachability. Mutation transformations
remain heuristic, and mutation score is not proof of COLREG semantic correctness.
The syntax helper is not a parser. Cross-platform agent copies are checked for
identity; actual Windows/OpenCode execution was not tested in this Linux environment.
JAR configuration is documented reference data; callers pass CLI options explicitly.
