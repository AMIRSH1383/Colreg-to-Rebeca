# Preserved experiments

`rule22a-run01/` and `rule19-run01/` are the original independent Codex agent
extractions from the supplied COLREG excerpts. The Rule 22 directory also retains
its original run metadata, validation, and Persian review. Rule 19 originally
contained only extraction.json; no historical metadata has been invented.

`toolchain-smoke/` preserves the earlier small model, property, result, and
onboarding logs. These historical results do not certify the original full model
or the migrated code. Old absolute paths and comments are intentionally unchanged.
Original copies remain outside the checkout under /workspace/colreg-runs and
/workspace/colreg-smoke in this environment; these locations are not portable.
Generated C++, binaries, and statespaces were not imported into Git.
