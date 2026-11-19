# Synthesis

Use the current Cloud session for the LLM step; the Python command never
launches a nested CLI. It requires exactly one mode, --prepare-only or --response.
The retained invoke_codex function is legacy code and is not called by this workflow.

Managed permanent output mode is documented in the repository README:

```sh
python -m scripts.synthesis.synthesis --rule Rule22a --prepare-only
python -m scripts.synthesis.synthesis --rule Rule22a \
  --response output/work/Rule22a/synthesis-response.json
```

Prepare prints the request location in ignored output/work. Perform exactly one
current-session pass using agents/synthesis_agent.md, then save/import the actual
response. The schema and eligibility semantics have not changed. No full source
model, supplementary skills or handbooks are needed.

The managed runner validates current upstream stages and the saved Rebeca
inventory, computes in scratch and replaces experiments/Rule22a/synthesis only on
success. A failure records its diagnostics outside experiments and retains the
last successful model/Property. Preparing does not replace successful outputs.
run.json tracks hashes and invalidates downstream results after input changes.

Explicit --colreg/--binding/--rebeca/--model/--output-dir modes remain available
for scratch use without --rule. Existing explicit output directories are refused;
managed --rule mode safely updates the same permanent directory instead.

usage.json counts only runner-side calls (zero for imports); it cannot measure
current-session inference. For a hosted synthesis, record the session's one-pass
provenance separately and leave token counts null when unavailable.

Outputs: request.json, response.json, model.rebeca, model.property (only when a
supported assertion exists), model.diff, patches.json, report.json, usage.json.
The report includes every statement disposition, upstream unresolved concepts,
deterministic blocking reasons, source/result hashes, and verification=not_run.
A model copy with no patches retains its original bytes, including line endings.
No input is overwritten. Output directories are exclusively created.

Generation currently supports scalar numeric/boolean state invariants with
explicit comparisons, same-participant scope/condition dependencies, and all
instances of a bound class. Prohibitions negate the supplied comparison. Conditions
are antecedents, never standalone compliance assertions. The runner checks the
entire property against canonical rendering, preventing invented fields, actors,
thresholds and omitted antecedents. Every statement requires a disposition; an
eligible obligation may be left unresolved with a reason.

Eligibility is evaluated per statement. Missing mappings, unsupported comparisons,
type mismatches and unsupported scope remain hard blockers. A blocked scope also
blocks its dependents; an unrelated unresolved concept does not. Every actual
guard of a generated obligation must receive a context disposition.

Binding limitations and unit/semantic uncertainties are preserved per statement,
including uncertainties inherited from its guards. They permit only conditional
symbolic scalar checks, explicitly labeled in Property warning comments and in
the report. Such checks use source thresholds without conversion; they do not
assert model units, physical visibility, qualifier coverage, or compliance.
All-round range can be checked symbolically while its absent color semantics
remain unresolved. The report retains original extraction assumptions and
external references. Unscoped assumptions remain visible for all candidates
because the upstream contract does not identify which statements they affect.
New state, behavior, temporal translations and non-scalar relationships remain
unsupported. No missing semantics are silently supplied.

Patches use exact UTF-8 byte ranges, full source and section hashes, unique exact
anchors, and overlap rejection. The runner permits only fresh pure boolean
observation helpers using supported canonical expressions at supplied class
closing braces. Direct field assertions need no helpers: prefer an empty patch
list. Constructors, initializers, handlers and scheduling cannot be edited. The
generic patch engine can apply other authorized ranges, but this runner does not
authorize them. Structural extraction is not compilation or semantic verification.
No Rebeca compiler, RMC, handbook, reference branch, or existing agent is invoked.

Synthetic fixtures in tests exercise the runner; they are not Rule 22(a) outputs.
The portable synthesis agent copy is maintained alongside its canonical file;
the existing sync_agents.py only handles the extractor and remains unchanged.
