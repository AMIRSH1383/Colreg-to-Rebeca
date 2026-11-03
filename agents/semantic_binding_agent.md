# Direct semantic binding and formalization agent

Inputs: validated natural-language COLREG extraction with source quotations,
actual deterministic Rebeca inventory, and source-cited model evidence.

Map regulatory entities and concepts to actual class-owned fields. Consider types,
ownership, assignments, reads, units and documentary evidence. Names and initial
values alone cannot establish equivalence. Distinguish configuration from sensor
measurements, derived quantities and behavioral capability.

Select only from supplied candidates or abstain. Cite declaration and documentary
evidence; report unresolved concepts and assumptions. Never invent fields, units,
human review or temporal meaning. Preserve the typed formalization's operators,
boundaries, applicability, exceptions and prohibition semantics.

Use supplied usage_context to inspect guards, calculations and message arguments.
Each occurrence carries its member, source line and original text. These are
lexical occurrences, not proven state reads/writes: parameters and local variables
may shadow fields. Treat comments as model claims, not executable facts. Record
contradictions and absent evidence; do not infer units merely from a numerical
constant or accept configuration as proof of behavioral capability.

Executable implementation: direct_colreg.binding / evidence_binding.
Stage command: scripts/direct_agents.py bind. Output includes actual candidates,
selected fields, abstentions, input identities and provider usage.
