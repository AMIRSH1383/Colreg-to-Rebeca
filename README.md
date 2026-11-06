# COLREG-to-Rebeca

Research tooling for translating natural-language COLREG regulations directly
into verifiable Rebeca models and properties, without manually written Legata.
The objective is to minimize unnecessary LLM calls and reuse deterministic tools.

## Pipeline and current status

| Stage | Status |
|---|---|
| 1. COLREG Extractor (LLM) | Implemented as agent instructions and a JSON contract |
| 2. Rebeca Extractor (deterministic Python) | Implemented partial structural extraction |
| 3. Semantic Binding & Formalization | Planned |
| 4. Synthesis | Planned |
| 5. RMC Verification | Existing reusable tooling; full pipeline integration pending |
| 6. Reporting | Planned; historical reports are evidence, not a reporting implementation |

## Layout

- `agents/`: canonical LLM instructions; `.opencode/agents/` is a synchronized copy.
- `schemas/`: extraction and verification contracts.
- `inputs/colreg/`: supplied Rule 19(a,b) and Rule 22(a) excerpts, not complete rules.
- `inputs/rebeca/original_model.rebeca`: original model, preserved unchanged.
- `skills/`: Rebeca handbook, mutation guidance, and retained Python verification tools.
- `scripts/`: development and heuristic syntax-check utilities.
- `tests/`: active tests; `archive/` is excluded from normal discovery.
- `experiments/`: preserved extraction outputs, metadata, reviews, and toolchain evidence.
- `archive/rebecai/`: old documentation, Legata baselines, FSM/acceptance tests.
- `output/`: ignored scratch/build output; do not store unique research evidence here.

## Development dependencies

Python 3.10+, Java 11+, and **g++** are required for verification. The runner
currently compiles with g++; clang alone is insufficient. RMC is an external JAR.
Use an isolated virtual environment, never a global package installation:

```bash
python3 -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

RMC 2.14 download URL and SHA-256 are recorded in `configs/rmc_defaults.json`.
Download from that official release over verified HTTPS and check the hash before
use. Set `RMC_JAR` to the downloaded JAR. No credentials are required.
The JSON config records reference defaults; CLIs do not automatically load it.
Resolver precedence: `RMC_JAR`, `RMC_DESTINATION/rmc.jar`, legacy local/home
`.claude/rmc_path[.txt]` markers, `~/.rebeca/rmc.jar`, local `.agents/rmc/rmc.jar`,
then legacy `~/.claude/rmc/rmc.jar`. An explicit missing environment path does not
silently fall back. Verification CLIs retain explicit `--jar` for reproducibility.

## Run the COLREG Extractor

Load `agents/colreg_extractor.md` into your LLM runner (OpenCode discovers its
platform copy). Supply these fields, from the repository root:

```text
rule_id: Rule-19
colreg_input: inputs/colreg/Rule19_baseline_colreg.txt
output_file: output/rule19/extraction.json
```

This is an LLM extraction instruction, not a Python extraction command or an
automatically registered Codex agent. Runner-specific invocation differs.
Validate the resulting JSON against `schemas/colreg-extractor.schema.json` using
`jsonschema`; check source grounding and cross-references separately. No automatic
claim of identical outputs across independent LLM runs is made.

Edit only the canonical agent, then run `python scripts/sync_agents.py`.
`python scripts/sync_agents.py --check` detects platform-copy drift. The portable
copy avoids symlink requirements on Windows. The existing prompt is unchanged.

## Run the Rebeca Extractor

```bash
python scripts/rebeca_extractor.py --input inputs/rebeca/original_model.rebeca \
  --output output/rebeca_extraction.json
python -m pytest -q tests/test_rebeca_extractor.py
```

The extractor uses only the standard library. Validate its JSON against
`schemas/rebeca_extraction.schema.json` (tests use the existing `jsonschema`
development dependency). Output includes classes, state declarations, instance
bindings, constructor-value candidates and a syntactic method/write index.
It does not evaluate general expressions, initialize arrays, or analyze control
flow, timing, or transitive method effects. Missing initialization fields are not
proof of zero/default values; unresolved values must remain unknown downstream.
Helper signatures/bodies are intentionally compacted. Semantic Binding remains
unimplemented. See `experiments/rebeca-extractor-review/` for the original-model
review. Generated snapshots and test logs remain local and are not committed.

## Verification

```bash
python skills/rebeca_tooling/scripts/verify_gate.py \
  --jar "$RMC_JAR" --model path/to/model.rebeca \
  --property path/to/model.property --rule-id Rule22 \
  --output-dir output/Rule22/run01 --output-file output/Rule22/result.json \
  --output-json
```

The gate distinguishes `satisfied`, `violated`, `unknown`, `execution_failed`,
`compilation_failed`, and `verification_failed`. Compilation is never a semantic
pass. The runner exports and parses the model-checker result; missing semantic
evidence remains unknown. Check `verified`, `passes_gate`, and `optional_checks`.
Append `--vacuity --mutation` to enable optional diagnostics. Disabled checks are
explicitly distinct from unknown/not-run checks. The legacy vacuity heuristic
compares a property with a negated assertion expression; it is **not** a general
logical antecedent reachability proof. Mutation errors are not killed mutants.

For parse/compile only, use `run_rmc.py` with the same input flags. Exit zero
means parse/compile success only. Add `--run-model-outcome --output-json` for
semantic checking. Run either CLI with `--help` for timeouts and export options.
Use dedicated generated-output directories; stale C++/executable artifacts are
removed before a new build. The gate writes `output/work/<rule_id>/verification.json`;
legacy output-policy step names remain accepted for existing consumers.
`model_out.outcome` retains its legacy process-exit classification; use
`verification_outcome` or the gate status as the semantic verdict. RMC may also
report implicit safety failures such as deadlock, not only named assertions.

## Validation

```bash
python -m pytest -q -m 'not requires_rmc'
bash tests/run_integration_tests.sh
python scripts/sync_agents.py --check
bash tests/leakage_scanner.sh
python scripts/validate-tooling.py
```

Real-toolchain tests are marked `requires_rmc` and skip with an explicit reason
if the JAR, Java, or g++ is unavailable. A skipped test is not a pass. Lint/type
checks are independent of runtime tests and should also pass before review.
`python scripts/check_rebeca_syntax.py file.rebeca file.property` is only a
heuristic for selected forbidden patterns, not a Rebeca parser.

## Research preservation and attribution

Existing JSON outputs and historical metadata are preserved unchanged, including
old absolute paths. See `experiments/README.md` for provenance and
`archive/rebecai/preservation.json` for original SHA-256 checksums and revision.
The original model has no dedicated reference property file in this checkout;
handbook examples are illustrative, not substitutes for one.

Derived from **RebecAI**, the Legata-to-Rebeca project documented in
`archive/rebecai/README.md` (upstream: https://github.com/3brahimi/RebecAI).
Retain `LICENSE` and upstream attribution. Historical Legata material is kept for
research comparisons, including separately identified Istanbul Strait case studies.
