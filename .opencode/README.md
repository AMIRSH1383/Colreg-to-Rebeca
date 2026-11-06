Agent instructions are maintained only in `agents/`. The OpenCode file is a
byte-identical generated copy for portable Windows/Git checkouts.
After editing the canonical prompt, run `python scripts/sync_agents.py`.
CI/local checks can run `python scripts/sync_agents.py --check`.
Do not edit `.opencode/agents/colreg_extractor.md` independently.
