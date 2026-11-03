# Evaluating the Rebeca extractor

Run these commands from the repository root in PowerShell. Python's standard
library is sufficient for local evaluation:

```powershell
python scripts/evaluate-extractor.py
python tests/test_extractor_evaluation.py
python tests/test_extract_rebeca.py
Get-Content work/evaluation/report.md
```

The first command performs an actual bounded downstream workflow:

1. Read and extract `work/Original Model.rebeca`.
2. Compare the inventory with `original_model_reference.json`, authored from the
   source rather than serialized from the extractor's output.
3. Validate explicit Rule22 bindings using only the inventory's variable types
   and instances. Check requirement quotations against the supplied rule text.
4. Generate ten instance-qualified properties and compare with the separately
   authored `rule22_expected.property` file.
5. Generate 18 separate model/property pairs: lengths 49, 50 and 51, each with
   compliant ranges and each of the five ranges individually one below minimum.
6. Interpret the generated predicates against each static scenario and compare
   with an independent expected outcome. Write JSON and Markdown reports.

Expected local results: 66/66 structural facts match, precision and recall 1.0,
seven selected constructor assignments match, reference properties match, and
18/18 static scenarios agree. The independent test runners contain nine workflow
and mutation tests plus three initial extractor tests. A mutation test passes
when the expected source change is followed or the intended error is detected.

Mutation checks cover renaming a variable (reject old binding; accept updated
binding), adding a ship (generate five additional properties), changing a
constructor argument, inserting comments with braces, missing/invented/mistyped
inventory fields, a changed assignment, priority-annotated message servers and a
wrong property threshold. These checks exercise the evaluation's ability to
detect errors instead of only testing successful extraction.

## Inspectable artifacts

- `work/evaluation/inventory.json`: extraction from the original source.
- `work/evaluation/binding.json`: explicit experimental mapping and assumptions.
- `work/evaluation/model.property`: generated original-instance properties.
- `work/evaluation/scenarios/`: isolated static model/property pairs.
- `work/evaluation/report.json`: metrics, differences, assumptions and outcomes.
- `work/evaluation/report.md`: readable results and scenario table.

The source and rule hashes in the JSON report identify the evaluated text.
Reference coverage is explicitly bounded: complete classes, state variables,
known rebecs, message signatures and main arguments, plus selected assignments.
Environment declarations, helper methods, array assignments, general expression
evaluation and behavior are not scored. Precision/recall count exact structural
facts including types and arguments; a wrong type counts as both a missing
expected fact and an unexpected fact. Constructor assignments are checked
separately. The fixtures require independent human review before use as a
publication-quality reference dataset.

## Real RMC verification

With a compatible RMC JAR, Java and `g++` available, request actual verification:

```powershell
python scripts/evaluate-extractor.py --output-dir work/evaluation-rmc --rmc-jar "C:\path\to\rmc.jar"
```

The runner uses the existing `run_rmc_detailed` interface for each scenario,
preserves logs/results in unique run directories, and accepts only parsed result
artifacts after successful generation, compilation and executable launch.
Missing tools, compilation failures and unrecognized results cannot count as
successful verification. When RMC is requested, the command exits nonzero unless
all actual verdicts match expectations. Timeouts are 60 seconds for generation
and the existing runner's default for model execution; compilation follows the
existing runner's behavior.

Real RMC has not been run in this environment: the expected JAR and `g++` are
unavailable. The generated syntax and checker integration therefore still need
real toolchain validation. Static predicate evaluation is not model checking.
Length 49 cases intentionally exercise out-of-scope implication behavior; length
50/51 cases exercise applicability, including ten expected violations.

This evaluates inventory usefulness for a fixed mapping. It does not evaluate
automatic natural-language extraction or semantic binding, prove a behavioral
abstraction of the original large model, or establish full regulatory compliance.
Units are explicitly assumed and the external Annex intensity requirement is
unresolved. Original constructor lengths 12 and 10 are not silently changed.
