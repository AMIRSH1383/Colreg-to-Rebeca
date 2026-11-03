# Milestone 3: source-evidenced semantic binding

Completion follow-up: see `REMAINING_WORK.md` for the evidence still needed for
full-source coverage. The independent frozen-property boundary suite produced
21/21 expected checker outcomes, including explicit uncovered all-round mutations.
Results: `work/milestone3/boundaries-001/summary.json`. This is not 21 regulatory
requirements verified; the suite deliberately demonstrates missing coverage.

This milestone adds a source-cited catalog and strict v2 binding path. It does not
use regulatory translations, rule-specific mapping tables, expected extraction
JSON or relaxed confidence thresholds. Milestone1/2 results remain unchanged.

## Audit and evidence

- `SEMANTIC_FINDINGS.md`: critical source findings and suitability assessment.
- `model-audit.md`: all 58 state fields across the navigation model and fixture,
  with class/instance ownership, declarations, writes, reads, transitions, units,
  meaning status, role, suitability, citations and uncertainty.
- `configs/model_evidence_annotations.json`: explicitly attributed analyst notes.
- `configs/evidence_model_catalog.json`: v2 catalog combining notes and actual
  lexical field evidence; exact model/source hashes and source quotations.

No annotation claims human review. The navigation light-range units remain
unknown, and geometric length/speed scaling conflicts are explicitly recorded.
Those fields cannot pass the strict evidence gate simply because old experiments
assumed a unit. Engine-on is not promoted into readiness, and simulated LIDAR
data is not promoted into radar semantics.

The isolated fixture's existing header documents metres and nautical-mile
visibility ranges. Header, declaration/category and constructor evidence support
configured-attribute checks only. They do not establish optical sensing, real
equipment installation, colored-light meaning, photometry or physical compliance.

## Rebuild the audit

From the repository root:

```powershell
python scripts/audit_model_semantics.py --model "work/Original Model.rebeca" --model examples/rule22a/range-model.rebeca --annotations configs/model_evidence_annotations.json --output work/milestone3/rebuilt-catalog.json
python scripts/render_model_audit.py --catalog work/milestone3/rebuilt-catalog.json --output work/milestone3/rebuilt-audit.md
```

The catalog writer refuses to overwrite a file. Source quotations and hashes are
validated before semantic claims are accepted. The analysis is bounded lexical
def/use analysis, not a full parser or proof of reachable transitions. Possible
local shadowing is flagged and excluded from attributed state operations.

## Binding policy

`scripts/direct_colreg/binding.py` dispatches v2 catalogs to
`scripts/direct_colreg/evidence_binding.py`. The v1 path is preserved for the
earlier regressions. V2 verifies model hash, actual declared field/type, exact
source citations, documentation of units, declared meaning scope and absence of
known contradictions before offering a candidate to the LLM.

The LLM receives actual documentary evidence and state-use information; source
concepts remain independent extraction output. It can select only a finite actual
candidate or abstain. A selected field must cite its declaration and documentary
support. Invented citations, missing ownership, contradictory units,
indistinguishable documented meanings and confidence below the unchanged 0.9
threshold cannot be accepted. Initial values are not allowed as mapping hints.

These are **LLM-assisted, evidence-constrained** decisions, not deterministic
semantic proofs or human-reviewed mappings. The confidence number is still
uncalibrated. The catalog's mappings list is empty; no Rule22 answer aliases
were inserted. Known semantics absent from evidence remain unresolved.

## Run the frozen evaluation

The existing authenticated Codex CLI and jsonschema are required. Java, RMC and
g++ are required for actual verification. Exact command used on this machine:

```powershell
$env:PYTHONPATH='D:/Research/research-RebecAI/.experiment-deps'
python scripts/evaluate_evidence_binding.py --output work/milestone3/evaluation-001 --jar D:/Research/research-RebecAI/output/experiments/toolchain/rmc.jar --wsl Ubuntu --timeout 30
```

Use a new output path to repeat it. The related-repository paths provide packages
and the checker only, never regulatory translations or historical results.
Native environments omit `--wsl` and use an appropriate JAR path.

The evaluator first snapshots and hashes the implementation, prompt/schema,
provider configuration, v2 catalog/annotations, test fixture code and input
models. It checks unchanged fingerprints between cases. It then performs four
**real LLM binding tests**:

| Case | Evidence | Expected behavior |
| --- | --- | --- |
| Positive | Nonsemantic variable q with explicit hull-length documentation | Bind q |
| Negative | Requested ocean depth but model documents hull length and beam width | Abstain |
| Ambiguous | Two fields with identical documented meaning | Abstain; initializer values cannot disambiguate |
| Renamed | q renamed but documentary meaning retained | Bind the renamed field |

These are synthetic binding-only tests, not prerecorded regulatory extraction.
The evaluator then makes a fresh actual LLM extraction of the authoritative
Rule22(a) clause, performs evidence-based binding, generates properties and runs
actual RMC plus independent applicability checking. It also checks that the
navigation model's uncertain units do not pass the evidence gate.

The production command for the same strict catalog is:

```powershell
python scripts/direct_colreg.py --source examples/rule22a/source.txt --rule-id Rule-22a --model examples/rule22a/range-model.rebeca --catalog configs/evidence_model_catalog.json --jar D:/Research/research-RebecAI/output/experiments/toolchain/rmc.jar --wsl Ubuntu --timeout 30 --output work/milestone3/new-direct-run
```

## Observed frozen result

All four actual binding tests passed and the frozen hashes stayed unchanged.
Five of six measurement concepts were resolved: vessel length and the masthead,
side, stern and towing range attributes. The four generated range obligations
were actually VERIFIED by RMC and applicability was reachable.

The all-round colored-light concept remained unresolved: no model source evidence
establishes the white/red/green/yellow scope. Annex I intensity also remains
unsupported. Therefore whole-source status is **UNSUPPORTED_SEMANTICS**, with
**supported_subset_status: VERIFIED** and full_source_verified false.
Do not describe this as complete Rule22(a) verification. The development probe
resolved more fields, illustrating why repeated inference cannot substitute for
independent semantic review; the conservative frozen result is retained.

The original navigation model was not changed or declared verified. Its units,
state semantics and compiler issues remain separate blockers. No metadata was
added after the frozen run to manufacture the missing color interpretation.

## Tests and negative checker evidence

```powershell
python -m pytest tests/test_evidence_binding.py tests/test_direct_colreg.py tests/test_rule22_milestone.py tests/test_run_rmc_execution_interface.py tests/test_extract_rebeca.py tests/test_extractor_evaluation.py --basetemp work/milestone3/pytest-temp -q
python scripts/check_bound_property.py --run work/milestone3/evaluation-001/rule22a --field masthead_light_range --from-value 6 --to-value 5 --expected VIOLATED --output work/milestone3/negative-rmc-001 --jar D:/Research/research-RebecAI/output/experiments/toolchain/rmc.jar --wsl Ubuntu
```

The focused suite passed 57 tests and 13 subtests, retaining all previously passing
Milestone1/2 tests. Mocked protocol/validation unit cases are not counted as real
LLM tests. The state-mutation command changes only a new isolated fixture copy,
reuses the frozen generated property unchanged and records actual checker XML.

Evidence paths: `work/milestone3/evaluation-001/summary.json`,
`rule22a/bindings.json`, `rule22a/report.json`, `rule22a/verification/result.xml`,
and `rule22a/applicability-0/result.xml` under the evaluation folder. Raw provider
requests/responses, usage, logs and counterexamples are retained separately.
Execution outputs are ignored by Git; source/catalog/audit documentation remains
reviewable. See `work/milestone3/RESULTS.md` for the critical summary.
