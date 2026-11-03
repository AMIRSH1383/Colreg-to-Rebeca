# Milestone 1: direct Rule22(a) visibility-range experiment

This runnable pipeline reads only the supplied natural-language clause and Rebeca
inputs. It does not read historical specifications, translations or experiment
results. No JEV or inference API is invoked.

## Prerequisites

Python 3.9+ with `jsonschema` (dependencies in `requirements.txt`), Java compatible
with your RMC JAR, and `g++`. Tests using pytest additionally need pytest. Either
use a native toolchain or an already installed Ubuntu WSL toolchain. Toolchain
installation is outside this milestone's entry point.

From the repository root, the exact command used on this machine was:

```powershell
$env:PYTHONPATH='D:/Research/research-RebecAI/.experiment-deps'
python scripts/rule22_pipeline.py --model examples/rule22a/range-model.rebeca --jar D:/Research/research-RebecAI/output/experiments/toolchain/rmc.jar --wsl Ubuntu --timeout 30 --scenarios --output work/milestone1/run-004
```

That dependency path supplies existing Python packages only. The JAR path supplies
the checker only; no related-repository research inputs or historical results are
read. WSL in this machine has Java on PATH. If necessary, add `--java-bin` with the
Windows path of an existing Linux Java `bin` directory mounted into WSL.

Use a **new output directory** for every run. The command refuses to overwrite an
existing directory. Omit `--output` for a unique timestamped directory.

For a native Linux/macOS toolchain:

```bash
python scripts/rule22_pipeline.py --model examples/rule22a/range-model.rebeca --jar /path/to/rmc.jar --timeout 30 --scenarios
```

To attempt the unchanged navigation model rather than the isolated model:

```powershell
python scripts/rule22_pipeline.py --jar D:/Research/research-RebecAI/output/experiments/toolchain/rmc.jar --wsl Ubuntu --timeout 30 --output work/milestone1/navigation-001
```

`--model` defaults to `work/Original Model.rebeca`. Optional `--property path`
inserts generated definitions/assertions into a copied property, preserving
unrelated text and sections. The input model is always copied byte for byte.
The reserved `M1_` namespace prevents silent collisions. Existing files are never
patched in place. New sections follow RMC's required define-before-Assertion order.

## What extraction means in this milestone

The executable built-in extractor is a **closed deterministic grammar for the exact
supplied excerpt**. It is not a general natural-language model and has no LLM
accuracy/cost claim. It emits the existing `schemas/colreg-extractor.schema.json`
contract, validates it with Draft 2020-12, checks source quotations, IDs,
dependencies, exact thresholds/units/roles, and saves source spans separately.
Changed wording is rejected instead of silently reusing fixed requirements.

To use the existing semantic extraction prompt, provide `agents/colreg_extractor.md`
with `rule_id: Rule-22a`, the source path, and an output file through your agent
host. The pipeline can validate and consume the returned artifact:

```powershell
python scripts/rule22_pipeline.py --extraction-json path/to/extraction.json --model examples/rule22a/range-model.rebeca --jar path/to/rmc.jar --scenarios
```

The external artifact must use this milestone's concept names (`vessel_length`,
`light_intensity`, `masthead_light_range`, `sidelight_range`, `sternlight_range`,
`towing_light_range`, `all_round_light_range`), roles, canonical units (`metres`,
`nautical_miles`) and exact semantics. Unknown variants fail closed. Upstream LLM
usage is unavailable unless supplied separately; the report does not invent it.

## Binding and formalization

The explicit reviewed name table in `rule22_pipeline.py:REVIEWED_NAMES` maps only
the six required measurement concepts to actual `Ship` state variables. Binding
requires the actual variable to exist with type `int` and finds actual Ship
instances. No fuzzy guesses or model variable additions are made. Missing or
mistyped fields block synthesis and appear in `binding.json` with a separate
extension proposal.

The authoritative interpretation is length **>=50 metres**, masthead **>=6
nautical miles**, and the other four ranges **>=3 nautical miles**. Each instance
gets atomic propositions and five applicability implications. Range values in
the original model have no machine-readable unit declaration: their units are a
declared experimental interpretation, explicitly reported, not an inferred fact.
The isolated fixture declares those units by construction.

The Annex I reference and unresolved intensity obligation are preserved.
This experiment does **not** establish full Rule22 or regulatory compliance.

## Actual RMC verification and applicability

Generation, compilation and model execution are distinct phases. A zero exit code
and successful compilation never establish a semantic verdict. The execution
runner exports fresh XML, accepts only explicit RMC report verdicts, rejects stale
output directories, and preserves logs. Unknown reports, deadlock, tool failures
and timeouts cannot count as satisfaction. Assertion-failure results are checked
against a label in the submitted property; available counterexample traces are
saved separately.

For each instance the pipeline also checks `!M1_<instance>_scope` in a separate
property file. A specific assertion-failure counterexample proves applicability
is reachable; satisfaction proves it is unreachable. Unknown remains unknown.
Original-model tool failures skip redundant applicability attempts.

`--timeout 30` bounds each generation, compilation and exploration phase, with an
additional outer driver budget. Increase to `--timeout 120` if needed. This is
not a total-suite limit; 18 cases each need verification and applicability runs.
Timeouts are reported honestly. Removing bounds is not supported by this entry
point because unrestricted exploration could run indefinitely.

## Scenarios and artifacts

`--scenarios` generates 18 isolated models: lengths 49, 50 and 51, each with
compliant ranges and five individual ranges one below minimum. The expected
outcomes are independent of generated predicates:

| Length | Compliant ranges | One deficient range | Applicability |
| --- | --- | --- | --- |
| 49 | satisfied, vacuous | satisfied, vacuous | unreachable |
| 50 | satisfied, non-vacuous | assertion violation | reachable |
| 51 | satisfied, non-vacuous | assertion violation | reachable |

The models maintain a constant self-message loop so finite execution does not
introduce an unrelated deadlock. They test static range semantics and are not a
proven abstraction of the original navigation model.

Each run contains `source.txt`, schema-validated `extraction.json`,
`source-spans.json`, `inventory.json`, `binding.json`, copied `model.rebeca`,
generated `model.property`, `report.json` and `report.md`. Verification directories
retain phase logs, `details.json`, `result.xml`, and counterexample XML when
available. Scenario folders additionally contain `case.json` and both property
files. The report records source/model/prompt/schema/JAR hashes, mappings, gaps,
units, actual verdicts, witness paths, vacuity, wall times and inference metadata.

Exit 0 requires a conclusive submitted-model verdict and, when requested, all
scenario expectations to match. An actual violation is a valid scientific verdict;
it does not mean compliance. Exit 1 records blocked/incomplete execution or a
failed scenario expectation. Always read `report.json`.

## Tests

Exact focused regression command on this machine:

```powershell
$env:PYTHONPATH='D:/Research/research-RebecAI/.experiment-deps'
python -m pytest tests/test_rule22_milestone.py tests/test_run_rmc_execution_interface.py tests/test_extract_rebeca.py tests/test_extractor_evaluation.py --basetemp work/milestone1/pytest-temp -q
```

The milestone tests also run as `python tests/test_rule22_milestone.py` with only
jsonschema installed. They exercise schema/source grounding, boundaries, missing
bindings, preservation, property ordering, explicit applicability, strict XML
evidence, stale results, timeouts and unsafe gate acceptance.

## Observed results on this machine

The focused suite passed **34 tests and seven subtests**. The actual RMC run in
`work/milestone1/run-004` passed **18/18** case expectations in approximately
**273.6 seconds**, including ten intended range violations. All six length-49
cases were correctly vacuous; applicability was reachable for all length-50 and
length-51 cases. The submitted isolated compliant model was satisfied and
non-vacuous. The JSON field `original_model` means the submitted baseline model;
in run-004 this is the isolated range model, not the navigation model.

`work/milestone1/external-json-001` additionally verified loading extraction JSON
and preserving `ExistingLengthNonnegative` alongside the generated assertions:
satisfied, non-vacuous. This validates the JSON interface, not an LLM extraction.

## Original-model blockers and proposed separate changes

The unchanged navigation-model probe is recorded in
`work/milestone1/navigation-001/report.json`. RMC reported double-to-int return
type mismatches at original source lines 293 and 846. Both `round(double)` methods
return `(int)x + dec` where `dec` is a double. The smallest compatibility candidate
is an explicit cast of `dec` after confirming it is always -1, 0 or 1. This is a
proposal for a separately reviewed model copy; no such patch is applied here.

That issue is distinct from missing Annex intensity semantics. Full intensity
verification would require the external specification, a reviewed physical model,
units and relevant behavior. Adding an unconstrained boolean would not establish
that requirement. Original ship lengths 12 and 10 also do not exercise the >=50
condition under the experimental metre interpretation.

Initial short-budget, ordering and deadlock probes are retained in run-001 through
run-003 with interruption notes. They are failed probes, not experiment successes.
Historical research result directories are untouched.
