# Rule 22(a): corrected RMC build verification

RMC derivative: 2.14-colreg-timing.1
SHA-256: 9aab24c776dad1b869b5b4770748980870cf1b583f7aa7cb4daa86579ebcee0e

The existing verification gate was used unchanged, selecting the corrected JAR
through its existing --jar option. Language 2.1 and FTTS defaults, original model,
Property, priorities, queue capacities, and initial values were retained.

- Java C++ generation: succeeded, with after/deadline expressions preserved.
- g++ compilation: succeeded; compiler stderr is empty.
- model.out: executed and exited 0 within its existing 30-second bound.
- XML semantic result: satisfied; 5470 reached states, 6512 transitions,
  reported model-checking time 23, and an empty counterexample trace.
- Gate: verification_status=satisfied, verified=true, passes_gate=true.
- All ten named synthesized checks occur in generated C++ and are called.
- No queue overflow, assertion counterexample or deadline failure was reported.
- No host execution errors occurred. SLF4J emitted nonfatal NOP-logger warnings.

This result establishes satisfaction of the encoded checks for this model/tool
configuration. It does not establish meaningful regulatory compliance. Raw
ship_length values are 12 and 10; only constructor assignments to that state are
present in generated actor behavior. The untranslated >=50 guards therefore
raise a strong vacuity concern. No dedicated antecedent reachability or vacuity
check was run. Vacuity and mutation remain disabled, exactly as in the baseline.
Missing units, physical visibility, intensity and color semantics remain open.
The gate's passes_gate=true must be read with its optional_checks=disabled.

Evidence: verification.json, rmc/model_result.xml, workflow.stderr.log,
rmc/rmc_stderr.log, rmc/compile_stderr.log, command.json and execution.json.
The existing runner discards runtime checker stdout/stderr; no console logs were
fabricated or recovered. Both checker exits and exported XML support this result.

Build evidence: timing-preflight.json records the checksum, two byte-identical
builds, exact changed JAR entries, and two packaged-JAR timing smoke tests.
44 pytest regression tests passed, none failed or skipped. Existing sources,
Synthesis artifacts, prior research outputs and upstream JAR were verified
unchanged by SHA-256. No verification architecture changes, commits or pushes.
