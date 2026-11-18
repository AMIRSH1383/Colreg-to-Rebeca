# Rule 22(a) Verification milestone

Recorded result from the existing RMC verification workflow using the actual
Synthesis outputs and corrected local RMC derivative `2.14-colreg-timing.1`.
This documents the completed run; committing this record does not rerun RMC.

## Result and execution

| Phase | Recorded result |
| --- | --- |
| Timed C++ generation | Successful; source after/deadline expressions retained |
| g++ compilation | Successful; empty compiler stderr |
| Checker execution | Completed, exit code 0 |
| Exported XML result | satisfied |
| Reached states / transitions | 5470 / 6512 |
| RMC reported checking time | 23 seconds |
| Whole workflow elapsed time | 57.58 seconds |
| Counterexample trace | Empty |
| Queue overflow, assertion counterexample, deadline failure | None reported |
| Gate status | satisfied; verified=true; passes_gate=true |
| Optional vacuity / mutation checks | Disabled / disabled |

The XML labels the checked property `Reachability` / `Deadlock-Freedom and No
Deadline Missed`. All ten named synthesized range checks are present and invoked
in the generated C++. No named assertion violation was reported. This result is
satisfaction of the encoded model checks, not complete COLREG formalization.
The original unpatched RMC run reported a queue overflow; corrected timing
eliminated that failure in this completed run without changing the input model.

The JAR was selected through the existing --jar argument. Language version 2.1,
FTTS, Java-generation timeout 120 seconds and checker timeout 30 seconds remained
the existing defaults. The original model, generated Property, initial values,
queue capacities, actor priorities and agent implementations were unchanged.
No verification improvements or new verification logic were introduced.

## Limitations

- Raw ship_length initial values are s1=12 and s2=10, below the untranslated
  >=50 antecedents. Static inspection found only constructor assignments to
  that actor state in generated behavior. This raises a strong vacuity concern;
  no dedicated antecedent reachability or vacuity check was run.
- Gate passes_gate=true must be read with optional_checks=disabled. It does not
  certify non-vacuity or mutation adequacy.
- The Property consists of conditional symbolic candidates. Length/range units
  and physical visibility semantics are unestablished; no conversion is implied.
- Intensity/Annex I and the all-round-light color qualifiers remain unresolved.
  Regulatory compliance has not been established.
- The unchanged runner discards checker console stdout/stderr. Exported XML,
  generator logs, compiler stderr and workflow diagnostics were retained.
- SLF4J emitted nonfatal NOP-logging warnings. No host execution error occurred.

## Build, reproduction and evidence

See [the timing-fix build documentation](../../tools/rmc-timing-fix/README.md)
for the two callbacks, pinned upstream provenance, reproducible build command,
and unchanged verification command. Two independent builds produced identical
JARs. Packaged-JAR generation regressions passed in 2.1/FTTS and 2.3/TTS.

Local research artifacts are deliberately excluded from this commit. A fresh
checkout does not recover these local-only files, including Semantic Binding
JSON, generated Synthesis outputs, logs or the binary JAR; do not fabricate them.
The exact recorded command is in output/Rule22/verification-timing-fixed/command.json.
The gate result is verification.json; raw XML is rmc/model_result.xml; logs are
workflow.stderr.log, rmc/rmc_stderr.log and rmc/compile_stderr.log under that
same directory. The original failed run remains under output/Rule22/verification/.

## SHA-256 provenance

| Recorded file | SHA-256 |
| --- | --- |
| `inputs/rebeca/original_model.rebeca` | `cb1bd2ae7a1c9637785c9d7f55d5bc6224299ea3d8d1795b77a6197580a8bc66` |
| `output/Rule22/synthesis/model.rebeca` | `cb1bd2ae7a1c9637785c9d7f55d5bc6224299ea3d8d1795b77a6197580a8bc66` |
| `output/Rule22/synthesis/model.property` | `7c5d81e387e9c3299d15ec21d4663ec377614a9aa631c4814f20cec67f1e3ed9` |
| `output/Rule22/semantic_binding.json` | `8e782d58ef8bf1c304291c43ad52e17a74257cdf9fe4f3b8efbbf1864001b7fb` |
| `output/rebeca_extraction.json` | `7fd0f730be770a96813f9438a11d3a946c057b942ba85a57160044cc65044760` |
| `output/Rule22/verification-timing-fixed/rmc/model_result.xml` | `71f972ff457634a5c944e519915e54f6fff8cd35aab254c92bdf46bc80875222` |
| `output/toolchains/rmc-2.14-colreg-timing.1/rmc-2.14-colreg-timing.1.jar` | `9aab24c776dad1b869b5b4770748980870cf1b583f7aa7cb4daa86579ebcee0e` |

## Publication regression checks

Before committing this milestone, 144 relevant pytest regressions passed with
zero failures or skips. These cover archive/build safeguards, the existing RMC
runner, resolver, result parser and gate, Synthesis/patching, and both upstream
extraction/binding stages. This regression run did not rerun RMC verification.
