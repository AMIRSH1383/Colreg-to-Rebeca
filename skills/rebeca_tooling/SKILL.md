---
name: rebeca-tooling
description: Deterministic RMC execution, result parsing, verification gates, mutation and vacuity diagnostics.
---

# Rebeca verification tools

Modules live in `skills/rebeca_tooling/scripts/`. They support package imports
and direct CLI execution. Run a CLI with `--help` for its complete options.
No LLM is needed to execute them. Python 3.10+, Java 11+, g++, and RMC are required.

- `run_rmc.py`: parse, generate C++, compile; optionally execute the checker and
  parse its exported result. Exit 0 alone means parse/compile success.
- `rmc_result_parser.py`: XML/text semantic results (`satisfied`, `cex`, `unknown`).
- `rmc_resolver.py`: environment variables, legacy markers, portable JAR locations.
- `verify_gate.py`: semantic verdict plus optional vacuity/mutation diagnostics.
- `mutation_engine.py`: deterministic mutation generation and bounded execution.
- `vacuity_checker.py`: legacy negated-expression comparison heuristic.
- `output_policy.py`: shared artifact paths; old numbered paths remain compatible.
- `utils.py`: path normalization and executable helpers, not a security sandbox.

```bash
python skills/rebeca_tooling/scripts/verify_gate.py \
  --jar "$RMC_JAR" --model model.rebeca --property model.property \
  --rule-id Rule22 --output-dir output/Rule22/run01 --output-json
```

Append `--vacuity --mutation` to enable optional diagnostics (CLI defaults: off).
`verified` requires semantic satisfaction. Unknown, execution failures and
counterexamples never pass. `optional_checks` distinguishes disabled, not_run,
unknown, passed and failed. `schemas/verification.schema.json` defines the output.
`--output-file` writes an atomic JSON artifact; stdout in JSON mode contains JSON
only and diagnostics go to stderr. The gate also writes
`output/work/<rule_id>/verification.json` under the selected `--base-dir`.

Use dedicated output directories. Keep final research inputs and selected evidence
in `inputs/` and `experiments/`; generated builds belong in ignored `output/`.
See README for JAR discovery and installation; config is reference documentation,
not automatically loaded. Scoring, reporting and the new upstream stages are not
implemented in this checkout.
