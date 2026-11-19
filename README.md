# COLREG-to-Rebeca

Translate natural-language COLREG rules into source-grounded extractions,
semantic bindings, conditional Rebeca properties and RMC results. The initial
Rule 22(a) pipeline completed with a corrected RMC timing compiler; its satisfied
result has unresolved vacuity and regulatory-semantics limitations. A Coordinator
Agent is not implemented. No supplementary skills or handbooks are loaded.

```text
agents/                       Canonical prompts: extraction, binding, synthesis
.opencode/agents/             Byte-identical portable copies
inputs/{colreg,rebeca}/       Original research inputs (never rewritten by runners)
schemas/                      Unchanged stage contracts
scripts/
  extraction/                 Deterministic Rebeca extractor
  binding/                    Semantic Binding runner/response validation
  synthesis/                  Compact request, response validation, exact patches
  utilities/                  Agent sync, syntax/lint checks, experiment lifecycle
verification/                 Existing RMC runner, parser, resolver, gate and diagnostics
  rmc/configs/                Original and corrected-build reference configurations
  rmc/timing_fix/             Reproducible compiler patch, builder and smoke model
tests/{extraction,binding,synthesis,verification,integration}/
experiments/{Rule22a,Rule19ab}/ Permanent small research outputs and run.json
output/                       Ignored scratch, builds, C++, binaries, statespaces, logs
```

## Setup

Python 3.10+ is supported; install the development requirements in a virtual
environment. RMC also requires Java and g++; timing-fix packaging needs a JDK
with source-file launching. OpenJDK 21 and g++ 14 were used for the recorded run.

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

The original model SHA-256 is
`cb1bd2ae7a1c9637785c9d7f55d5bc6224299ea3d8d1795b77a6197580a8bc66`.
Both original tracked COLREG input files are preserved. They were locally
deleted before migration and safely restored from Git during finalization;
no input text was reconstructed or altered.

## Per-rule workflow

Use `--rule Rule22a` or `--rule Rule19ab`. Each stage writes the designated files
in that rule's existing directory. Computation occurs under ignored output/work;
publication occurs only after successful validation. A failure keeps the last
successful payload and records the failed attempt. Hash changes mark dependent
stages stale. Consumers inspect run.json; file existence alone is not validity.
See [experiment lifecycle](experiments/README.md) for details and limitations.

1. Execute agents/colreg_extractor.md in the current session with its unchanged
   inputs/contract, writing a candidate under output/work. Publish the authentic
   returned extraction (this command does not invoke an LLM):

```sh
python -m scripts.utilities.experiments publish-colreg --rule Rule22a \
  --source output/work/Rule22a/colreg-response.json
```

Supply `--colreg-input inputs/colreg/<actual-file>.txt` when the original text is
available. Without it, raw-source provenance is explicitly incomplete.

2. Extract the original Rebeca model deterministically:

```sh
python -m scripts.extraction.rebeca_extractor --rule Rule22a
```

3. Execute agents/semantic_binding_agent.md using the existing two inventories
   and its compact projection; import the actual response:

```sh
python -m scripts.binding.semantic_binding --rule Rule22a \
  --response output/work/Rule22a/binding-response.json
```

The binding runner's original explicit-input/provider mode remains available;
response import avoids a nested CLI in hosted environments. No automatic repairs.

4. Prepare synthesis, perform one current-session pass using
   agents/synthesis_agent.md, and import its actual response:

```sh
python -m scripts.synthesis.synthesis --rule Rule22a --prepare-only
python -m scripts.synthesis.synthesis --rule Rule22a \
  --response output/work/Rule22a/synthesis-response.json
```

The first command prints the compact request path under output/work/Rule22a.
The runner checks all hashes, mappings, actors, thresholds and guards, then
applies source-anchored patches to a copy. The original model is never changed.
See [synthesis documentation](scripts/synthesis/README.md).

5. Build the pinned, separately versioned RMC derivative, then use the existing gate:

```sh
python -m verification.rmc.timing_fix.build \
  --input-jar /path/to/original/rmc-2.14.jar \
  --output-dir output/toolchains/rmc-2.14-colreg-timing.1
python -m verification.verify_gate --rule Rule22a --no-vacuity --no-mutation
```

The managed gate selects the corrected JAR from
verification/rmc/configs/rmc_timing_fixed.json, unless `--jar` overrides it.
The reference JSON is not an implicit configuration loader for low-level tools.
See [timing fix](verification/rmc/timing_fix/README.md) and
[verification tooling](verification/README.md). Process/compile success is not
semantic satisfaction. Unknown, compilation failures and execution failures do
not replace a completed managed verification result; violations are valid
completed results and are published as such. Optional diagnostics are distinct
from the semantic verdict.

All stage CLIs retain explicit input/output modes for isolated scratch work.
Direct script paths and `python -m` both work; old flattened paths have moved.
Do not point scratch outputs at permanent experiments or bypass run.json checks.

## Development checks

```sh
python -m pytest -q -m 'not requires_rmc'
python -m scripts.utilities.sync_agents --check
python -m scripts.utilities.validate_tooling
bash tests/integration/leakage_scanner.sh
```

Set RMC_JAR to an existing corrected build to enable the small real-toolchain
fixtures: `python -m pytest -q -m requires_rmc`. These are isolated synthetic
checks, not another full Rule 22(a) research experiment. Generated artifacts stay
outside tracked experiments. Tests are grouped by stage and run from a fresh
checkout without the removed legacy implementation.

The original license remains in LICENSE; see [ATTRIBUTION.md](ATTRIBUTION.md).
Migration details and compatibility limits are in [MIGRATION.md](MIGRATION.md).
