# RebecAI

Run the two downstream stages separately: [semantic binding and synthesis agents](examples/direct-agents.md).

Milestone 3 adds [source-cited model evidence and strict semantic binding](examples/milestone3/README.md).
It preserves the previous milestones and does not change the navigation model.

Milestone 2's generic production entry point is
[`scripts/direct_colreg.py`](scripts/direct_colreg.py): it invokes the configured
LLM for extraction and does not contain rule-specific answers. See the
[Milestone 2 commands and critical limitations](examples/milestone2/README.md).
The Rule 22(a) runner below is retained as a historical regression fixture.

The direct Rule 22(a) milestone is runnable through
[`scripts/rule22_pipeline.py`](scripts/rule22_pipeline.py). See
[exact reproduction commands, scope and blockers](examples/rule22a/README.md).
It uses natural-language input, deterministic binding/synthesis and actual RMC
XML verdicts, with separate applicability checks and isolated boundary scenarios.

For the direct natural-language COLREG research direction, see
[the implementation and evaluation plan](FUTURE_WORK_PLAN.md). The initial
deterministic model inventory is runnable without extra dependencies:

```powershell
python skills/rebeca_tooling/scripts/extract_rebeca.py "work/Original Model.rebeca" --output work/analysis/original-model.inventory.json
```

Evaluate extraction accuracy and its use in Rule 22 property generation:

```powershell
python scripts/evaluate-extractor.py
python tests/test_extractor_evaluation.py
```

See [evaluation instructions and limits](tests/evaluation/README.md), including
the optional real RMC run. Local static scenario checks do not run model checking.

A multi-agent orchestration (MAO) system for transforming maritime safety rules from Legata formal specifications into verifiable Rebeca actor models, automated via the Rebeca Model Checker (RMC).

## Overview

RebecAI provides a unified framework to:
- **Transform** formal specifications (Legata/COLREG) into verifiable Rebeca actor models
- **Automate** model checking workflows using RMC
- **Verify** properties using mutation scoring and vacuity checks
- **Report** verification outcomes through automated tooling

## Repository Structure

| Category | Path | Purpose |
| :--- | :--- | :--- |
| **Agents** | `agents/` | Coordinator + 4 specialist subagents |
| **Skills** | `skills/` | Reusable knowledge injected at subagent startup |

## Quick Start

```bash
# Clone and install
git clone https://github.com/3brahimi/RebecAI.git
cd RebecAI
python3 setup.py

# Preview what would be installed (no writes)
python3 setup.py --dry-run

# Remote install (no clone required)
curl -sSL https://raw.githubusercontent.com/3brahimi/RebecAI/main/setup.py | python3 -

# Clean up all installed artifacts before re-install
python3 purge.py && python3 setup.py
```

## Invoking the Agent

The coordinator agent is named `legata_to_rebeca`. Below are copy-paste prompt templates for each supported platform. Fill in the four required values before sending.

**Required values**

| Placeholder | What to provide |
|-------------|-----------------|
| `<rule_id>` | Short identifier, e.g. `Rule-22` |
| `<legata_file>` | Path to the Legata `.txt` rule file |
| `<reference_model>` | Path to the reference `.rebeca` model |
| `<reference_property>` | Path to the reference `.property` file |

---

### Claude Code

```
@legata_to_rebeca

Transform <rule_id> to Rebeca.

rule_id:            <rule_id>
legata_input:       <legata_file>
reference_model:    <reference_model>
reference_property: <reference_property>
output_dir:         output
```

Run inside the project directory where RebecAI is installed (`~/.claude/agents/legata_to_rebeca.md` must exist). The agent has Bash access and will call the tooling scripts directly.

---

### Gemini CLI

```
@legata_to_rebeca

Transform <rule_id> to Rebeca.

rule_id:            <rule_id>
legata_input:       <legata_file>
reference_model:    <reference_model>
reference_property: <reference_property>
output_dir:         output
```

Run from the project root. Gemini CLI loads agents from `~/.gemini/agents/`. The agent file is a physical copy with Gemini-incompatible frontmatter keys stripped by the installer.

---

### GitHub Copilot Chat

Select the `legata_to_rebeca` agent in the Copilot Chat agent picker, then send:

```
Transform <rule_id> to Rebeca.

rule_id:            <rule_id>
legata_input:       <legata_file>
reference_model:    <reference_model>
reference_property: <reference_property>
output_dir:         output
```

The agent file lives at `.github/agents/legata_to_rebeca.agent.md`. Copilot Chat runs a single agent context — there are no spawned subagents. The coordinator executes all eight steps itself in sequence.

---

**Concrete example (COLREG Rule 22)**

```
Transform Rule-22 to Rebeca.

rule_id:            Rule-22
legata_input:       `colreg/Rule22.txt`
reference_model:    `rebeca/reference.rebeca`
reference_property: `rebeca/reference.property`
output_dir:         `output/`
```

## Architecture: Multi-Agent Orchestration

`legata_to_rebeca` is a **coordinator** that delegates each pipeline step to a specialist subagent. Each specialist runs in its own context window, calls deterministic Python scripts via `Bash`, and emits a structured JSON contract back to the coordinator.

```
legata_to_rebeca (coordinator)
├── Step03 → abstraction_agent    extract actors, discretize variables
├── Step04 → mapping_agent        generate .rebeca model + .property file
├── Step05 → synthesis_agent      LLM-assisted candidate generation (parallel)
├── Step06 → verification_exec    RMC + vacuity check + mutation scoring
├── Step07 → packaging_exec       collect and package artifacts
└── Step08 → reporting_exec       score (100-point rubric) + reports
```

## Agents & Skills

### Coordinator + Specialists

| Agent | Step | Description |
| :--- | :--- | :--- |
| `legata_to_rebeca` | Coordinator | Orchestrates Step03–Step08, manages shared_state |
| `abstraction_agent` | Step03 | Extracts actors, applies naming conventions, discretizes variables |
| `mapping_agent` | Step04 | Generates `.rebeca` model and `.property` file |
| `synthesis_agent` | Step05 | LLM-assisted candidate property generation (requires Step06 validation) |
| `verification_exec` | Step06 | Runs RMC, vacuity check, mutation scoring |
| `packaging_exec` | Step07 | Collects and packages pipeline artifacts |
| `reporting_exec` | Step08 | Produces per-rule scorecards and aggregate reports |

### Skills

| Skill | Used by | Purpose |
| :--- | :--- | :--- |
| `rebeca_tooling` | All specialists | Schemas + script documentation; 14 Python dumb tools |
| `rebeca_handbook` | abstraction, mapping, synthesis, verification, reporting | Modeling best practices |
| `legata_to_rebeca` | Coordinator | Workflow guidance |
| `rebeca_mutation` | verification_exec | Mutation testing patterns |

## Installation Details

`setup.py` installs agents and skills to `~/.agents/` (the primary truth copy) then creates platform-specific links:

| Target | Location | Format |
|--------|----------|--------|
| Claude Code | `.claude/agents/` | Symlinks; full frontmatter including `skills:` |
| Gemini CLI | `.gemini/agents/` | Physical copies; Gemini-incompatible keys stripped |
| GitHub Copilot | `.github/agents/` | Symlinks with `.agent.md` suffix |

`~/.agents/skills/` is a **shared namespace** — third-party skills (grepai, graphify) coexist with Rebeca's 5 owned skills. The installer only copies/links skills it owns and never overwrites unrelated entries.

## Requirements

- **Python 3.8+** | **Java 11+** (for RMC) | **C++ compiler** (g++/clang)
- **Platforms:** ✅ macOS · ✅ Linux · ✅ Windows

## Contributing

To add agents, skills, or dumb tools: follow the structure in `agents/` and `skills/` and run `python3 setup.py` to install.
