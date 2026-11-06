---
name: rebeca-handbook
description: Rebeca modeling and property-writing guidance for the retained RMC toolchain.
---

# Rebeca modeling guidance

Actors have local state and communicate using asynchronous message servers.
Declare actor instances and known-rebec references in `main`; initialize state in
constructors. Keep finite domains and bounded nondeterminism for model checking.
Timed models may use `after` and `deadline`; preserve these when extracting data.

Property files contain named `define` predicates and labeled `Assertion` entries.
For assertion implication use `!antecedent || consequent`. LTL has its own temporal
syntax and can use `->`; do not apply assertion-only restrictions indiscriminately.
Declare referenced variables and actor instances. Avoid chained assignments and
parameter/state-variable shadowing. Use parentheses to make grouping explicit.

Examples in `examples/` are illustrative; only a successful actual RMC invocation
establishes parser/compiler compatibility. Domain examples are not authoritative
COLREG interpretations. Rule 22(a)'s supplied length boundary is >= 50 metres.

Run the tools documented in `skills/rebeca_tooling/SKILL.md`. Parsing and compiling
are distinct from semantic property satisfaction. Inspect exported result artifacts,
counterexamples, skipped checks, and unknown results. Never silently equate a
compile success with verification. Preserve the original reference model unchanged.
