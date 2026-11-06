# Deterministic Rebeca Extractor integration review

This report records the initial integration review of the three supplied
implementation/schema/test files at their requested paths on main. The ZIP README and example
were treated as supporting material, not instructions. Extraction was performed
only by Python, without LLM agents or Rebeca skills. No Semantic Binding was added.

## Validation and source accuracy

All 11 provided tests passed before corrections. After adding focused regressions,
21 extractor tests pass via both pytest and unittest. Repository unit validation
reports 184 passed, 0 failed, 0 skipped. The 13 RMC-specific tests were deselected
(NOT RUN for this integration); verification code was not changed.
The supplied schema is unchanged and validates the generated result. Repeat CLI
execution against the original model produces byte-identical output. The original
model SHA-256 matches its pre-integration hash:
`cb1bd2ae7a1c9637785c9d7f55d5bc6224299ea3d8d1795b77a6197580a8bc66`.

| Extracted structure | Ship | MapServer | Total |
|---|---:|---:|---:|
| Classes | 1 | 1 | 2 |
| Instances | 2 | 1 | 3 |
| State variables | 46 | 6 | 52 |
| Message servers | 3 | 3 | 6 |
| Helpers | 31 | 21 | 52 |

There are 45 environment constants. Independent source checks matched all 52 state
names/types/dimensions, class names, constant count and message-server names.
Method header anchors were checked against the source (annotations may precede
the method signature). Every extracted constructor-expression anchor matches its
source assignment. Main's s1/s2/theMap classes, priorities, constructor arguments
and reciprocal knownrebec links were reviewed against the three source declarations.
Core structural sections also match the example supplied in the ZIP; that example
is corroborating evidence, not an independent ground truth for semantic accuracy.

All scalar state variables have constructor-assignment candidates: 43 Ship and 5
MapServer variables. Across instances, 77 values resolve and 14 remain unresolved.
For example ship_length resolves to 12/10, ship_dir to 2, vis_range to 1200,
engine_on to true, and allround_light_range to 2, exactly as written. No values were
changed to fit COLREG expectations.

## Targeted parser corrections

- Exclude env-looking text inside strings from constant extraction.
- Treat equality as an expression, not a constructor assignment.
- Invalidate a prior initialization candidate after a later conditional/compound
  write, rather than claiming a fixed earlier value.
- Recognize comma-separated locals when excluding shadowed state-write candidates.
- Split declaration semicolons outside strings and reject unterminated declarations.
- Prevent output via a hard link from overwriting the input model.

These fixes leave the original model's class/instance/constant/summary structures
identical to the supplied example. Runtime dependencies remain standard-library only;
schema validation uses the repository's existing jsonschema development dependency.

## Limits affecting Semantic Binding

Seven distinct Ship values remain unresolved (14 instance entries):
`distance2target`, `max_waiting_rounds`, `default_time_cross`,
`default_time_cross_diag`, `default_velocity`, `ship_velocity`, and
`original_velocity`. They contain casts, arithmetic, function calls or state-value
references. Their expressions remain available; do not treat them as numeric values.

The four array states `obstacles`, `targets`, `moves`, and `ship_loc_dir_vel` have
no scalar initialization field. Their indexed/loop initialization is omitted from
fixed values, not absent from the source. Absence is not proof of default zero or
of an uninitialized runtime variable.

State-write indexing is syntactic, not control/data-flow analysis: local shadowing
is conservatively method-wide; explicit self-qualified writes, aliasing, transitive
helper effects and branch-specific final values are not comprehensively modeled.
Constructor candidates do not prove the final post-constructor value when helper
calls have effects. Writes through helpers are not attributed transitively to callers.
Only five source-line anchors per variable are retained; counts can exceed five.

Helper entries discard parameter/return signatures and bodies. Message-server
entries preserve parameters/priorities/writes but not reads, guards, dispatch,
after/deadline timing, message-call graphs or detailed behavior. Inline assertions
are text, not verified properties. Units and maritime meaning are not inferred.
The extractor handles a partial Rebeca grammar; it is not a compiler/parser validator
and does not reject every malformed or unsupported construct.

**Suitability:** usable as the structural symbol/instance inventory for Semantic
Binding, provided unresolved/missing data stays explicit and the original source
remains available for behavior, helper signatures, timing and domain interpretation.
It is not sufficient alone for complete semantic formalization. No general semantic
accuracy percentage is claimed from this single model.

The required CLI output remains at output/rebeca_extraction.json (ignored build
output). Local review copies, source-review.json, validation.json and test logs
were retained for inspection but deliberately excluded from the implementation
commit. Regenerate the extraction with the command in the root README.
