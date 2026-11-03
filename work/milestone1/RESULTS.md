# Milestone 1 execution evidence

No historical research assets or results were modified. Inputs are the supplied
natural-language source and Rebeca models; no intermediate regulatory language or
manual regulatory translation is used.

| Run | Scope | Actual result |
| --- | --- | --- |
| run-001 | Initial 10-second budget probe | Generation timeouts; interrupted; no success claimed |
| run-002 | Property syntax probe | RMC rejected section ordering; writer fixed; interrupted |
| run-003 | Initial static fixture | RMC reported deadlock; fixture given constant self-message loop; interrupted |
| run-004 | Isolated model plus 18 boundary/violation cases | Completed; 18/18 expectations matched; 273.583 seconds |
| navigation-001 | Byte-identical copy of original navigation model | RMC type errors at source lines 293 and 846; semantic verdict unknown; no applicability rerun |
| external-json-001 | Validated extraction JSON plus existing unrelated property | Satisfied and non-vacuous; 14.127 seconds |

The successful suite consists of six length-49 cases (satisfied but vacuous),
compliant cases at lengths 50 and 51 (satisfied and non-vacuous), and five
individual deficient light ranges at each of lengths 50 and 51 (ten actual
assertion violations). Each applicable case has a counterexample to the
explicit assertion that its applicability condition is absent.

`run-004/report.json` contains the complete stage artifacts and execution paths;
`run-004/scenarios/*/verification/result.xml` contains the checker verdicts.
The corresponding `applicability-s1/result.xml` files establish reachability or
unreachability. Available assertion traces are saved as `result.counterexample.xml`.

The field `original_model` refers to the model submitted to that run. For run-004
that is the isolated range model. Only navigation-001 submits the full navigation
model; no full navigation-model satisfaction is claimed.

The focused local regression command in `examples/rule22a/README.md` passed
34 tests plus seven subtests. The full legacy suite was not run. Real RMC evidence
is separate from these mocked/unit regression checks.

Pipeline inference calls: zero. The executable extraction is a closed parser for
the exact supplied text. The external JSON run validates the existing schema
interface, not an LLM's semantic quality. Token usage is unavailable/not applicable.

Scope limitations: Annex I intensity semantics remain unresolved, original-model
physical units require review, isolated models are not a proven abstraction of
navigation behavior, and the two existing model type errors need a separately
reviewed compatibility copy. See the milestone README for the proposed change.
