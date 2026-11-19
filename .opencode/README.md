Agent instructions are maintained only in `agents/`. The OpenCode files are
byte-identical generated copies for portable Windows/Git checkouts.
After editing the canonical prompt, run `python scripts/utilities/sync_agents.py`.
CI/local checks can run `python scripts/utilities/sync_agents.py --check`.
Do not edit `.opencode/agents/colreg_extractor.md` independently.

The synchronized names are `colreg_to_rebeca`, `colreg_extractor`,
`semantic_binding_agent`, and `synthesis_agent`. Invoke `@colreg_to_rebeca` for
the full workflow. The Coordinator uses the host's task tool when available
and otherwise follows the specialist instructions in the current session.
Native Synthesis delegation was tested in Codex. OpenCode native dispatch
remains untested. See [Coordinator usage](../scripts/coordinator/README.md)
for the tested workflow and CLI checkpoint protocol.
