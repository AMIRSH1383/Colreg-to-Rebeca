# Permanent rule artifacts

Rule22a contains the authentic paragraph (a) extraction, original-model Rebeca
inventory, supplied Semantic Binding response, current-session Synthesis output,
and successful corrected-RMC verification. Rule19ab contains the saved Rule 19
(a)/(b) extraction and the same saved original-model inventory. No binding,
Synthesis or verification output was available for Rule19ab; these are missing.
No LLM was rerun to populate artifacts during migration.

```text
Rule22a/
  colreg_extraction.json
  rebeca_extraction.json
  semantic_binding.json
  extraction/                 Original extraction provenance/review
  synthesis/                  Model copy, Property, response, report, hashes/usage
  verification/               result.json, model_result.xml, assessment, execution
  run.json
Rule19ab/
  colreg_extraction.json
  rebeca_extraction.json
  run.json
```

Payloads were migrated byte-for-byte. Embedded paths in historical JSON/reports
are frozen provenance from the actual run, not active inputs to a new execution.
The new run.json records canonical dependencies, hashes and freshness. Curated
README files contain current commands. No binary, generated C++, full statespace,
cache, failed candidate or historical smoke log belongs here.

## Controlled overwrite and failure handling

- Use the stage CLIs with --rule, not timestamp/run-number directories. An
  optional --experiments-dir supports isolated workspaces/tests.
- Computation and failed candidates stay under output/work/<rule>/<stage>/.
  --prepare-only updates a prepared request there without replacing the last
  successful synthesized model or Property.
- A rule-wide exclusive publication lock serializes stage attempts. A successful
  validated stage replaces only its designated artifacts. Files no longer
  produced by the new result (such as a Property when none is supported) are
  removed, so an old file cannot masquerade as a new result.
- A failed attempt preserves the last successful files. Its error/status is in
  last_attempt; last_success still identifies the preserved payload. A retry can
  succeed in the same directory without manual cleanup.
- run.json stores input and output SHA-256 values. Changed inputs, manual output
  edits, missing outputs, or stale upstream stages make downstream stages stale.
  Re-publishing identical content does not unnecessarily invalidate consumers.
- Publication checks inputs again before promotion. Copy errors roll back the
  previous payload. An interrupted multi-file publish is detected through hash
  mismatch rather than reported as valid. Consult status before consuming data.
- After an abrupt process termination, a leftover .publish.lock must be examined
  and removed only after confirming no stage is active. There is no automatic
  lock stealing. This local-filesystem protocol is not a distributed scheduler.
- During live publication or after a process crash, last_attempt=running denotes
  an incomplete attempt. Consumers must use current last_success hashes, not the
  in-progress attempt. Store-backed runners also enforce upstream freshness.

Inspect current validity, including changes made outside the runners:

```sh
python -m scripts.utilities.experiments status --rule Rule22a
```

The on-disk statuses are refreshed during managed attempts/publication; the status
command computes current validity at read time. Never treat a cached status or
file presence as sufficient. Removing an external response used as an input can
make its dependent stage stale; preserve authentic response files or import them
from a durable location.

Raw COLREG input files were missing during migration and were subsequently
restored byte-for-byte from their tracked Git versions before publication.
Historical migration provenance still records the earlier absence; payloads
were not rewritten or re-extracted to manufacture a new source-grounding result.
A fresh checkout contains the curated small outputs, but the ignored RMC JAR
must be rebuilt before a managed verification stage is current/executable.
This is intentional hash-based dependency checking, not permission to invent a
missing toolchain or output. Satisfied conditional assertions do not establish
non-vacuity, physical unit equivalence, or complete regulatory compliance.

Small exported verification XML reports (up to 1 MiB) are published alongside
result.json. Larger counterexample XML stays in retained ignored scratch, linked
from result metadata; full statespaces are never promoted to experiments.
