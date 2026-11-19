# Coordinator usage

Invoke the Coordinator once in OpenCode or a Codex Cloud session that can read
the repository and run Python. Use `@colreg_to_rebeca` where the host exposes the
registered prompt. In a Codex Cloud session without that launcher, instruct
Codex to execute `agents/colreg_to_rebeca.md` with `rule_id: Rule22a`. The host
follows the Coordinator instructions and continues its own handoffs.

```text
@colreg_to_rebeca

rule_id: Rule22a
```

Optional fields are `colreg`, `model`, and `jar` paths, and
`full_rerun: true`. Rule22a and Rule19ab select the corresponding tracked inputs.
For another rule, supply an explicit COLREG path. The model defaults to
`inputs/rebeca/original_model.rebeca`. Verification selects the pinned timing
build from `verification/rmc/configs/rmc_timing_fixed.json`. An alternate JAR
path must contain the same corrected build. Rebuild it using
`python -m verification.rmc.timing_fix.build` if it is missing.

The Python entry point runs the deterministic stages and final report directly.

```sh
python -m scripts.coordinator.pipeline --rule-id Rule22a --reuse
```

Reuse is the default. Pass `--full-rerun` to rerun all computational stages.
Terminal-only use needs an external host to respond to a checkpoint when a
specialist is required. The result then contains `status: awaiting_agent`,
the request file path, a response destination, and a request ID. The host
executes the indicated existing specialist and resumes with the same options
and `--resume REQUEST_ID --response PATH --execution native` or
`--execution same-session`. The checkpoint expires if a new invocation for
the same experiment replaces it. The Coordinator rejects a response if its
inputs or previously completed stages changed while paused.

The Coordinator prompt prefers native delegation when the host provides it.
When the host uses same-session execution, the specialist passes share
conversation context. Host dispatch requires a session able to read files,
write the response, and continue shell calls. The report counts specialist
passes reported by the host. Provider transport requests and token counts
are available only when the host supplies them.

## Validated execution

In an isolated Rule 22(a) experiment copy with the synthesis output removed,
the Coordinator reused both extractions and the binding and returned a
synthesis checkpoint. The Codex host delegated one real LLM pass to a native
Codex subagent using the canonical Synthesis prompt, its output schema, and
the compact checkpoint input. The host resumed the CLI with the returned
JSON. The response passed validation without edits or retries. The synthesized
model and Property matched the saved files byte for byte, so verification
reused the `satisfied` verdict from the earlier RMC run.

OpenCode native dispatch and a fresh end-to-end run of all LLM stages remain
untested. The standalone Python CLI uses checkpoints and resumes with
host-supplied responses whenever LLM inference is required.

The existing experiment store publishes stage results and tracks hashes.
Failed stages preserve their last successful artifacts and leave diagnostics
in ignored scratch. A valid partial synthesis can proceed to verification if
it produces a Property. Without a Property the Coordinator records a skip.
The RMC gate still defines its own verdict. The Coordinator includes its status
and the XML outcome, including queue overflow, when available. Optional
vacuity and mutation checks retain the existing disabled defaults.

The final report is `experiments/<rule>/coordinator_report.json`. It records
what happened in that invocation and can contain local log paths. Git ignores
the generated report. The reuse command above regenerates it from the tracked
Rule 22(a) artifacts and a matching pinned JAR. Use `python -m scripts.utilities.experiments
status --rule <rule>` to check freshness later. Failed invocations write their
report to ignored scratch and leave the last completed report in place.
