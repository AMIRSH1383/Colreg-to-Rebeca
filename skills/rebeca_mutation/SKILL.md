---
name: rebeca-mutation
description: |
  Orchestrates Phase1 (semantic mutation testing) of the Step06 verification pipeline.
  Generates controlled mutations of .rebeca model files and .property files,
  runs RMC on each mutant, and computes a Mutation Score. Integrates vacuity checking.
---

# rebeca-mutation
...

## When to invoke

Use `verify_gate.py` — it runs RMC, vacuity, and mutation in one call and returns `passes_gate`.
Do **not** invoke `vacuity_checker.py` or `mutation_engine.py` directly.

```bash
python3 <scripts>/verify_gate.py \
  --jar <jar> --model model.rebeca --property property.property \
  --rule-id Rule22 --output-dir output/Rule22 --output-json \
  --mutation  # Required to enable mutation-based testing (default: off)
```

| Trigger | Action |
|---------|--------|
| After Step05 synthesis | Run `verify_gate.py`; check `passes_gate` |
| During Step06 quality gate | Read `mutation_score` and `vacuity_status.is_vacuous` from gate result |

---

## Mutation Strategies

Eight strategies are implemented in
`<scripts>/mutation_engine.py`:

| ID | Target | What changes | Expected outcome |
|----|--------|-------------|-----------------|
| `transition_bypass` | `.rebeca` | Comments out a state-variable assignment inside `msgsrv` | Mutant should be **killed** (property detects missing transition) |
| `predicate_flip` | `.rebeca` | Negates an `if`-condition (`if (x)` → `if (!x)`) | Mutant should be **killed** |
| `assignment_mutation` | `.rebeca` | Increments a numeric literal by 1 (`= N` → `= N+1`) | Mutant should be **killed** |
| `comparison_value_mutation` | `.property` | Increments comparison constant in `define` block | Mutant should be **killed** |
| `boolean_predicate_negation` | `.property` | Negates a boolean term in an assertion (`x` → `!x`) | Mutant should be **killed** |
| `assertion_negation` | `.property` | Negates the full assertion expression | Mutant should be **killed** (RMC finds counterexample) |
| `assertion_predicate_inversion` | `.property` | Swaps implication sides (`A → B` → `B → A`) | Mutant should be **killed** |
| `logical_swap` | `.property` | Swaps `&&` ↔ `\|\|` in the assertion | Mutant should be **killed** |

---

## Mutation Score Formula

```
Mutation Score = (Killed Mutants) / (Total Mutants) × 100
```

- **Killed**: baseline vs mutant semantic outcome flips (`satisfied` ↔ `cex`).
- **Survived**: baseline and mutant semantic outcomes are identical.
- **Error**: baseline/mutant semantic outcome is unavailable (`unknown`/timeout/non-comparable).

Target threshold: **≥ 80%** to pass the Step06 quality gate.

---

## Output JSON Schema

The skill emits a JSON report compatible with the agent's scoring pipeline:

```json
{
  "rule_id": "COLREG-Rule22",
  "mutation_score": 87.5,
  "total_mutants": 16,
  "killed": 14,
  "survived": 2,
  "errors": 0,
  "vacuity": {
    "is_vacuous": false,
    "precondition_used": "!hasLight || (lightRange >= 6)",
    "explanation": "NON-VACUOUS: A counterexample exists for !Precondition; the property is meaningful."
  },
  "per_strategy": [
    {
      "strategy": "transition_bypass",
      "total": 3,
      "killed": 3,
      "survived": 0
    },
    {
      "strategy": "assertion_negation",
      "total": 1,
      "killed": 1,
      "survived": 0
    }
  ],
  "survived_mutations": [
    {
      "mutation_id": "logical_swap_0",
      "strategy": "logical_swap",
      "description": "Swapped && -> || at offset 142 in assertion",
      "artifact": "property"
    }
  ]
}
```

---

## Step06 Integration

During **Step06 (Verification)**, call `verify_gate.py` once. Read `passes_gate` from the result:

| `passes_gate` field | Meaning | Action |
|---------------------|---------|--------|
| `verified=false` | RMC parse/compile failed | Fix model or property |
| `vacuity_status.is_vacuous=true` | Property trivially satisfied | Strengthen assertion |
| `mutation_score < 80` | Weak property; mutants survived | Add missing cases |
| `passes_gate=true` | All criteria met | Proceed to packaging |

---

## Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Property has no `define` block | `comparison_value_mutation` generates 0 mutants | Expected — not an error; other strategies still run |
| All mutants survive | Mutation score = 0% | Property likely vacuous or too weak; rewrite assertion |
| Vacuity check times out (exit 3) | `is_vacuous = None` | Increase `--timeout-seconds`; model may be too large for secondary pass |
| Mutant compile error (exit 4) | Counted as "killed" in default mode | Correct — a mutation that breaks compilation still kills the mutant |
| `variable_swap` finds no pairs | Generates 0 mutants | Model has only one actor variable per namespace; not an error |
| Double-negation in negated property | `!!x` in vacuity file | `build_negated_property` simplifies this automatically |
