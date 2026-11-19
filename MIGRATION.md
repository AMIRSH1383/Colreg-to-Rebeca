# Structural migration

The three canonical prompts and their output schemas retain their semantics.
Only package paths, CLI publication destinations and execution metadata changed.
No LLM invocation or new full Rule 22(a) research run was used for migration.

| Previous location | Current location |
| --- | --- |
| scripts/rebeca_extractor.py | scripts/extraction/rebeca_extractor.py |
| scripts/semantic_binding.py | scripts/binding/semantic_binding.py |
| scripts/synthesis.py, apply_model_patches.py | scripts/synthesis/ |
| scripts/sync_agents.py, syntax/lint utilities | scripts/utilities/ |
| Verification Python module directory | verification/ |
| RMC configuration files | verification/rmc/configs/ |
| Timing patch, builder, documentation and fixture | verification/rmc/timing_fix/ |
| Flat tests | tests/<pipeline-stage>/ |
| Rule 22 paragraph (a) artifacts | experiments/Rule22a/ |
| Rule 19 paragraphs (a)/(b) artifacts | experiments/Rule19ab/ |

Legacy RebecAI source, Legata baselines, archived tests and schemas were removed
from the active tree as requested. Attribution and the original MIT LICENSE are
retained. Executable verification code was relocated before removing supplementary
skill/handbook material. No replacement implementations were imported from a
reference branch. New imports use verification.*, scripts.extraction.*,
scripts.binding.*, scripts.synthesis.* and scripts.utilities.*. Old flattened
Python/script paths intentionally have no compatibility shims.

A complete pre-migration repository backup and checksums were saved outside the
active repository, including unexplained input deletions and untracked review
artifacts. Obsolete validation/smoke outputs were removed from active experiments;
useful genuine stage outputs were migrated without changing their contents.
Historical source/run metadata may mention original locations. Those strings
are evidence, not paths that current code resolves. The current run.json records
new canonical dependencies. See experiments/README.md for overwrite/freshness
rules and the distinction between current state and recorded historical results.

The two previously deleted raw COLREG inputs were safely restored from their
identical tracked HEAD/index versions during approved finalization. Their text
and the original Rebeca model are unchanged from Git. Integration tests check
the original Rebeca and COLREG checksums along with prompts/contracts/LICENSE. Timing patch Java bytes, version and binary checksum remain unchanged.
The moved builder still creates the same pinned JAR; the existing verifier's
semantic functions, timeout defaults and result normalization are unchanged.

Managed --rule mode runs the existing stage implementation in ignored scratch,
then publishes its validated small outputs. Added binding --response imports an
existing response using the original result validator; it does not change the
binding contract or prompt. Verification filesystem paths in newly published
result metadata are relocated to retained scratch; the original semantic verdict
and schema remain unchanged. Recorded migrated JSON payloads are never rewritten.
The COLREG LLM output is published via a deterministic import utility because
there is no executable COLREG LLM runner to wrap. No Coordinator was introduced.

## Completed validation

- Full suite: 291 passed, including 13 small real RMC toolchain fixtures.
- Final local deterministic suite: 278 passed, 13 real-toolchain tests deselected.
- Fresh exported checkout: 278 passed; strict mypy and flake8 passed.
- Two relocated-builder builds and a fresh-export build matched the pinned JAR
  checksum 9aab24c776dad1b869b5b4770748980870cf1b583f7aa7cb4daa86579ebcee0e.
- All three OpenCode copies synchronized; 15 modules imported and eight direct
  script help commands worked from outside the repository.
- 21 authentic stage artifacts, original model, prompts, schemas and LICENSE
  verified byte-identical. Core semantic function/class ASTs compared in 14
  moved modules; no stage interpretation or verification behavior changed.
- Failure retention, safe overwrites, stale dependency rejection, rollback and
  concurrent publication protection covered by deterministic integration tests.
- No final test failures. No LLM agents or new full Rule 22(a) research run invoked.

Detailed local move/hash and validation evidence is in
output/migration-validation/report.json (ignored generated diagnostics).
