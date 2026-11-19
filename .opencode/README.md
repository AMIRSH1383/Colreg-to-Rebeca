Agent instructions are maintained only in `agents/`. The OpenCode files are
byte-identical generated copies for portable Windows/Git checkouts.
After editing the canonical prompt, run `python scripts/utilities/sync_agents.py`.
CI/local checks can run `python scripts/utilities/sync_agents.py --check`.
Do not edit `.opencode/agents/colreg_extractor.md` independently.

Synchronized agents: `colreg_extractor`, `semantic_binding_agent`, and `synthesis_agent`.
