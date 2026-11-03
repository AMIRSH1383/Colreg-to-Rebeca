# Direct synthesis agent

Input: validated binding handoff and exact source model/properties.
Executable implementation: direct_colreg.synthesis; scripts/direct_agents.py synthesize.

Generate atomic propositions and named assertions from validated semantic bindings
and typed logical expressions. Add only the required property entries and preserve
unrelated property sections. Render expressions deterministically, preserving the
supplied operators, numerical boundaries and units. Do not infer missing operators,
thresholds or model concepts.
Exceptions modify applicability; prohibitions negate the forbidden predicate.

Copy the model byte-for-byte into a new run directory. Save a modification manifest
and independent applicability-witness properties. Missing concepts are reported as
model-extension needs; do not add flags or initializations to manufacture success.
Reject inconsistent instance scopes and cross-entity relations. Temporal and
behavioral semantics outside the engine remain UNSUPPORTED_SEMANTICS.

Validate that all fields in each requirement refer to the same supported entity
and actor-instance scope. Stage a requirement completely before adding its
properties; failed rendering must leave no partial assertions. Use a fresh output
directory and reject existing generated artifacts rather than overwriting them.

Synthesis does not establish verification. Reuse the existing RMC backend and
classify actual XML results independently from compilation and exit status.
