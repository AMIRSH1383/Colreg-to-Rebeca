# Milestone 2: generic direct extraction and state verification

Production entry point: `scripts/direct_colreg.py`. The old
`scripts/rule22_pipeline.py` remains only for Milestone 1 regression tests.
The new entry point has no fixed COLREG thresholds, light categories, class names,
regulatory interpretation tables, extraction replay option or JEV integration.

## Real provider and dependencies

The provider is the existing authenticated Codex CLI, configured in
`configs/direct_provider.json`. The selected model was taken from the existing
local configuration. Authentication is checked with `codex login status`; no
credentials are copied into this repository. Python needs jsonschema; tests also
need pytest. No packages were installed during implementation.

Each request runs with `--ephemeral`, `--ignore-user-config`, a read-only sandbox,
and an empty working directory. Source and schemas are supplied inline. No expected
extraction, evaluator files, model mappings or rule-specific few-shot answers are
attached to extraction. Recorded tool use invalidates a source-only response.
This is procedural isolation plus a read-only sandbox, not proof that a provider
has no pretrained knowledge of the regulations.

The CLI's reported usage includes its own context overhead. Invocations are not
claimed to equal underlying provider request counts; the CLI may reconnect/retry.
Raw events, final responses, submitted prompts, schemas, latency and usage are
retained. Monetary cost is null because CLI subscription billing is unavailable.
Optional explicitly sourced per-million input/cached/output prices can be supplied
in the provider config; never substitute guessed prices or zero for unknown cost.

## Reproduce

From the repository root, using already available packages and toolchain on this
machine:

```powershell
$env:PYTHONPATH='D:/Research/research-RebecAI/.experiment-deps'
python scripts/direct_colreg.py --source examples/rule22a/source.txt --rule-id Rule-22a --model examples/rule22a/range-model.rebeca --catalog configs/direct_model_catalog.json --jar D:/Research/research-RebecAI/output/experiments/toolchain/rmc.jar --wsl Ubuntu --timeout 30 --output work/milestone2/new-run
```

Use a fresh output directory every time. Native Java/g++ environments omit
`--wsl` and use their own JAR path. `--property` optionally supplies an existing
property; unrelated sections are preserved and the input model is copied unchanged.
No related-repository regulatory inputs or historical results are read: those
machine-specific paths provide Python packages and the RMC JAR only.

For extraction alone:

```powershell
python scripts/extract_colreg.py --source path/to/clause.txt --rule-id any-rule-id --output work/milestone2/new-extraction
```

The first extraction attempt exposed an unsupported strict-schema keyword. A later
HTTPS fallback exposed missing explicit types on constant-valued fields. The
provider now translates only transport constraints and always validates the full
general schema locally. Failed attempts remain recorded; there is no silent
fallback to predefined semantics.

## Contracts and binding

The existing `agents/colreg_extractor.md` source-grounding instructions are reused,
with `agents/direct_semantic_contract.md` defining an inline v2 interface.
`schemas/colreg-semantic.schema.json` extends the old semantic concepts with typed
formalization. The old envelope is also validated independently against the old
schema. Quotations, ID uniqueness, dependencies, coverage of normative statements
and support for formal comparisons are checked. These structural checks do not
prove completeness or semantic correctness; independent review is required.

Typed logic supports scalar comparisons >, >=, <, <=, ==, !=; AND, OR, NOT,
implication; multiple applicability conditions; exemption predicates; and simple
state obligations/prohibitions. Temporal, relational and multi-entity requirements
abstain as UNSUPPORTED_SEMANTICS. Unsupported obligations are retained alongside
any generated supported subset, so subset verification never implies full coverage.

The existing deterministic Rebeca reader supplies actual fields/types/instances.
Candidate filtering rejects incompatible types, unknown dimensions and mismatched
units. There is no implicit unit conversion. Names rank candidates but similar
names alone do not automatically establish equivalence. Exact actor/concept identity
plus validated metadata can resolve automatically. Otherwise a separate bounded
LLM call selects only candidate IDs or abstains. Self-reported confidence is not
calibrated; selections below the conservative policy threshold abstain.

`configs/direct_model_catalog.json` is versioned and tied to exact model hashes.
Its current contents supply experimental units, not concept aliases or regulatory
thresholds; its `mappings` list is empty. Field descriptions are deliberately null
where independent semantic documentation is unavailable. This can cause correct
abstention, and did so during evaluation. Catalog-assisted semantic mappings, if
reviewed separately, use `model_sha256`, `entity`, `concept`, `field`, `evidence`
and method `catalog_assisted` or `manually_supplied`. Such additions must precede a
new evaluation freeze; they must not encode rule-specific expected answers.

`bindings.json` retains candidates, rejection reasons, metadata provenance,
selection method, evidence, confidence and abstentions. LLM-assisted choices still
need independent correctness assessment. Compatible units and high confidence are
not semantic proof.

## Verification outcomes

The existing RMC execution and strict XML parser are reused. Compilation and exit
codes alone never establish property satisfaction. Reports distinguish VERIFIED,
VIOLATED, VACUOUS, UNKNOWN, TIMEOUT, COMPILATION_ERROR and UNSUPPORTED_SEMANTICS.

All generated assertions are checked together. A separate negated effective
antecedent check establishes applicability per distinct condition and instance.
Identical checks are reused within a run. If at least one generated requirement
has unreachable applicability, a satisfied aggregate is marked VACUOUS; the
per-condition records show which branch is unreachable. This does not mean every
obligation is vacuous. Failures in unrelated preserved properties remain aggregate
failures; this prototype does not attribute every failure to one generated clause.

`full_source_verified` remains false pending independent semantic review.
`all_extracted_requirements_checked` concerns only the generated representation.
An earlier frozen cohort used an overstrong full-source flag; its raw report is
preserved and must not be treated as reviewed regulatory verification.

The evaluation uses isolated static models, not the full navigation model. The
original navigation model's Milestone 1 type errors remain unresolved and unchanged.

## Frozen evaluation and independent expected results

```powershell
python scripts/evaluate_direct_colreg.py --jar D:/Research/research-RebecAI/output/experiments/toolchain/rmc.jar --wsl Ubuntu --timeout 30 --rmc-boundaries --output work/milestone2/evaluation-002
```

The harness snapshots all generic implementation files, prompts, schemas, provider
config, catalog, model and backend; records Git HEAD and the tracked diff; and
hash-checks before and after each rule. Untracked source files are included in the
snapshot, so HEAD alone is not misrepresented as the implemented revision.
It never passes expected JSON into extraction. Test-only expected numerical
semantics live in the evaluator, not the production code or catalog.

Cases include authoritative user-supplied Rule22(a), formatting and paraphrase
variants, a synthetic ambiguous clause, a missing-model concept, a clearly labeled
synthetic interval/exception constraint, and Rule19(a-e). Rule19 source attribution
is in `provenance.json`, from UK MCA's MGN369 quoted rule text. Synthetic clauses
are not represented as real COLREG regulations.

Rule22(b) remains source-blocked pending the user's authoritative text. With a
reviewed source available before running a new frozen cohort, add
`--rule22b-source path/to/authoritative.txt`. The evaluator contains independent
boundary expectations at 11/12, 19/20 and 49/50 metres; these must be checked
against the supplied source. The generic engine receives no such expectations.

The harness performs static independent property checks and, with
`--rmc-boundaries`, actual checker runs on boundary and deficient-range fixtures
when a property was generated. No property means the boundary tests are explicitly
not run, not counted as passes. Semantics and binding correctness still require
review of saved source/AST/mapping evidence. Do not interpret schema acceptance
as semantic success.

The first cohort is retained at `work/milestone2/evaluation-001`. After that whole
cohort finished, a protocol-only schema fix and a report-claim correction were
made, and the implementation was frozen again for evaluation-002. No prompt or
catalog changes were made in response to unseen-rule results.

## Regression tests and actual renderer checks

```powershell
python -m pytest tests/test_direct_colreg.py tests/test_rule22_milestone.py tests/test_run_rmc_execution_interface.py tests/test_extract_rebeca.py tests/test_extractor_evaluation.py --basetemp work/milestone2/pytest-temp -q
python scripts/check_state_logic_rmc.py --jar D:/Research/research-RebecAI/output/experiments/toolchain/rmc.jar --wsl Ubuntu --output work/milestone2/renderer-rmc-001
```

The first command includes all previously passing Milestone 1 focused tests.
Synthetic unit-test ASTs test logic and validation only; they are never replayed
through the production extraction interface. The second command performs actual
RMC checks of interval/AND/OR/NOT logic, exceptions and prohibition polarity,
including a violation and an unreachable antecedent. It is explicitly a renderer
test, not evidence of real LLM extraction quality.

To independently reproduce the 18 actual boundary checks of the saved development
property (not as a fresh extraction or a passing frozen cohort):

```powershell
python scripts/evaluate_saved_properties.py --run work/milestone2/development-pipeline-001 --output work/milestone2/new-development-boundaries --oracle A --jar D:/Research/research-RebecAI/output/experiments/toolchain/rmc.jar --wsl Ubuntu --timeout 30
python scripts/report_direct_evaluation.py --cohorts work/milestone2/evaluation-001 work/milestone2/evaluation-002 --output work/milestone2/evaluation-report.md
```

Observed checks: 49 focused tests plus 13 subtests pass; all three actual synthetic
renderer/backend cases pass; saved development Rule22(a) properties match 18/18
independent states and 18/18 actual RMC outcomes. These successes do not erase the
frozen Rule22(a) binding failures. See `work/milestone2/RESULTS.md` for the critical
acceptance assessment and separate inference totals for both frozen cohorts.

Known limits: bounded regex-based Rebeca inventory, scalar state logic only,
no temporal or relational semantics, no automatic physical-unit discovery,
unreviewed LLM mappings, stochastic extraction/schema inconsistencies, provider
failures and unavailable financial billing. Three rules would not establish
arbitrary COLREG coverage even if every test succeeded.
