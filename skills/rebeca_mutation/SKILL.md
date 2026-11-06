---
name: rebeca-mutation
description: Controlled Rebeca model/property mutations and bounded semantic comparison using RMC.
---

# Mutation diagnostics

Use `verify_gate.py --mutation` for orchestration, or the mutation engine directly
for catalogs and focused debugging. Run either CLI with `--help`.

A mutant is killed only when comparable baseline and mutant semantic verdicts
flip between `satisfied` and `cex`. Parse/compile failures, timeouts and unknown
outcomes are errors, never kills. Sampling uses an explicit seed; budgets and
counts are included in the output. Score is killed / total_run * 100, including
errors in total_run. A zero-run or budget-limited/error-containing result cannot
pass the gate. The current threshold is 80 percent; it is a diagnostic threshold,
not a proof that a translation matches COLREG.

```bash
python skills/rebeca_tooling/scripts/verify_gate.py \
  --jar "$RMC_JAR" --model model.rebeca --property model.property \
  --rule-id Rule22 --output-dir output/Rule22/run01 --mutation --vacuity --output-json
```

Vacuity is a legacy negated-expression comparison heuristic, not a general
antecedent reachability proof. Unknown results remain unknown. Inspect each
optional-check status before interpreting a score. Original input models are
never mutated in place. Retain selected artifacts for research comparisons.
