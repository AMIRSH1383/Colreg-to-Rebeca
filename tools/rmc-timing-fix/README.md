# RMC 2.14 timing fix: 2.14-colreg-timing.1

This is a local, separately versioned derivative of the official RMC 2.14
release, not an upstream release or a complete upstream source rebuild.
The original JAR is never modified. Original licenses and attribution entries
are retained. The generated JAR remains an ignored build artifact.

The compiler bundled in the original JAR accepts after/deadline syntax but
TimedRebecaListener has no exitAfter/exitDeadline implementations. The grammar's
returned Expression e fields stay null; exitPrimary copies those nulls into
the AST. The translator then emits arrival=now and deadline=infinity.

Only two callbacks are added to that class:

```java
public void exitAfter(TimedRebecaCompleteParser.AfterContext ctx) {
    ctx.e = ctx.expression().e;
}
public void exitDeadline(TimedRebecaCompleteParser.DeadlineContext ctx) {
    ctx.e = ctx.expression().e;
}
```

No model, Property, initial values, scheduling statements, verification scripts,
queue bounds, language version, or FTTS/TTS selections are changed. The compiler
now preserves the scheduling statements already present in the source. This
changes the erroneous generated behavior to match those source annotations.

## Build and reproduce

Requires Python 3.10+ and a JDK with source-file launching (JDK 11+); tested with
OpenJDK 21.0.12.1. No network or additional dependencies are needed: Javassist
is already bundled in the checksum-pinned upstream JAR.

```sh
python scripts/build_rmc_timing_fix.py \
  --input-jar /workspace/.tools/rmc/rmc-2.14.jar \
  --output-dir output/toolchains/rmc-2.14-colreg-timing.1
```

The builder refuses an unexpected upstream hash or an existing output directory.
BuildTimingListener.java uses bundled Javassist to add the methods to a temporary
class copy. The Python builder repacks a new JAR, preserving every other entry's
payload, original order and metadata. Entries are ZIP_STORED to avoid zlib-version
variation. One deterministic META-INF/colreg-rmc-build.json entry records version,
upstream hash, patch source hash and patched class hash. No timestamps or local
paths enter this metadata. There is no upstream manifest version substitution;
the derivative's identity is this metadata, its filename and build.json.

Two independent builds on the recorded JDK produced byte-identical artifacts.
Repeat with a fresh --output-dir and compare SHA256SUMS. build.json also records
the JDK version; build.stdout.log and build.stderr.log retain Java diagnostics.

| Artifact | SHA-256 |
| --- | --- |
| Official rmc-2.14.jar | a39112046d99e0895cf47f890242ace21db896e609f7eef86751a0d416d477f5 |
| rmc-2.14-colreg-timing.1.jar | 9aab24c776dad1b869b5b4770748980870cf1b583f7aa7cb4daa86579ebcee0e |

## Use the existing runner

configs/rmc_timing_fixed.json records the pinned artifact. The existing tools do
not load this reference config automatically. Configure the run through their
existing --jar argument; RMC_JAR also selects this build in rmc_resolver.py.

```sh
python skills/rebeca_tooling/scripts/verify_gate.py \
  --jar output/toolchains/rmc-2.14-colreg-timing.1/rmc-2.14-colreg-timing.1.jar \
  --model output/Rule22/synthesis/model.rebeca \
  --property output/Rule22/synthesis/model.property \
  --rule-id Rule-22a \
  --output-dir output/Rule22/verification-timing-fixed \
  --base-dir output/Rule22/verification-timing-fixed/pipeline \
  --output-file output/Rule22/verification-timing-fixed/verification.json \
  --output-json --rmc-timeout 120 --no-vacuity --no-mutation
```

Use a fresh output directory for each run. Existing gate execution bounds remain:
120 seconds for Java generation and 30 seconds for model.out. Gate process exit
0 is not a semantic verdict: inspect verification.json and exported result XML.
Optional vacuity/mutation are disabled in this baseline. Timing preservation does
not establish compliance, source-unit equivalence, or antecedent reachability.

## Generation regression

The timing-smoke.rebeca fixture tests after-only, deadline-only, combined constant
annotations, variable expressions, and implicit self sends. With the corrected
JAR it emits arrival=now+rate and deadline=now+(rate+5), rather than now/infinity.
The actual packaged JAR was tested in 2.1/FTTS and 2.3/TTS before verification;
see output/Rule22/verification-timing-fixed/timing-preflight.json. Archive tests
also check unchanged payloads, reproducibility, input hash enforcement, signature
rejection and overwrite protection.

## Recorded Rule 22(a) milestone

The corrected build completed the existing workflow with an exported `satisfied`
result (5470 states, 6512 transitions), no reported queue overflow and no input
model changes. Vacuity was not checked, and regulatory semantics remain open.
See [the curated verification record](../../experiments/rule22a-verification/README.md)
for provenance, execution results and the limits of this satisfaction result.
