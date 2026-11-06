---
name: rebeca-tooling
description: Cross-platform Python library for RMC operations, scoring, and reporting
---

# Rebeca Tooling Skill

## RULE: Scripts Are Opaque CLIs — Never Read Source

**Do NOT read any `.py` file under `<scripts>/`.** Every script is a black-box CLI with a documented contract in this file. Reading source wastes tokens and provides no additional information — the CLI flags, exit codes, and JSON output schema documented here are the complete and authoritative interface. If something is undocumented here, run the script with `--help`.

---

## Purpose

This skill provides a cross-platform Python library for all Rebeca model checking operations, including:
- RMC download and execution
- Shared RMC jar path resolution (`rmc_resolver`)
- COLREG fallback mapping
- Single-call verification gate: RMC → vacuity → mutation (`verify_gate`)
- Single-rule scoring and aggregate reporting
- Per-rule comprehensive reporting (`generate_rule_report`)
- Multi-rule consolidation with publication-ready plots (`consolidate_reports`)

## When to Use

Use this skill when you need to:
- Download or execute the RMC model checker
- Resolve/probe `rmc.jar` deterministically across local/global installs
- Classify Legata rule formalization status
- Generate provisional properties from COLREG text
- Run the full verification gate (RMC + vacuity + mutation) in one call
- Score verification results
- Generate aggregate reports
- Generate comprehensive JSON/Markdown reports for an individual rule folder
- Consolidate many rule folders into one report with tables and bar/cactus plots (SVG+PNG)

## Library Location

All Python modules are in `<scripts>`:
```bash
ls <scripts>
```

## Python Library Usage

### Import from Skill

```python
import sys
from pathlib import Path

# Add skill's lib to path
skill_path = Path("<skills>/rebeca_tooling").expanduser()
sys.path.insert(0, str(skill_path))

from scripts import (
    run_rmc,
    resolve_rmc_jar,
    require_rmc_jar,
    RuleStatusClassifier
)
```

### RMC Operations

#### Run RMC Verification

```python
from scripts import run_rmc

result = run_rmc(
    jar=<jar>,
    model="path/to/model.rebeca",
    property_file="path/to/property.property",
    output_dir="verification_output",
    timeout_seconds=120,
    jvm_opts=["-Xmx2g"]
)

# Exit codes:
# 0: Success (parse + compile)
# 1: Invalid inputs
# 3: Timeout
# 4: C++ compilation failed
# 5: Rebeca parse failed

# For semantic details, use run_rmc_detailed() from run_rmc.py directly:
# - model_out.outcome (runtime executable outcome)
# - result_artifact.outcome (parsed from exported result file when available)
# - verification_outcome (resolved semantic verdict)
```

### Scoring and Reporting

#### Score Single Rule (TQC 9-Point Rubric)

```python
from scripts.score_rule import RubricScorer

scorer = RubricScorer()
scorecard = scorer.score_rule(
    rule_id="Rule-22",
    verify_status="pass",          # pass|fail|timeout|blocked|unknown
    rmc_exit_code=0,               # raw exit code from run_rmc_detailed()
    is_vacuous=False,              # from vacuity_checker; None = not run
    mutation_score=85.0,           # kill rate [0,100]; None = not run
    # TQC artifact inputs — pass directly when calling from Python.
    # The CLI derives these automatically from --output-dir + --rule-id.
    property_text="...",           # content of .property file
    variable_map={"speed": ...},   # from abstraction_summary.variable_map
    actor_map={"GiveWayVessel": ...},  # from abstraction_summary.actor_map
    concept_mapping={...},         # from step03_mapping.json concept_mapping
    rmc_stderr_content="...",      # from verify_gate rmc/rmc_stderr.log
    compile_stderr_content="...",  # from verify_gate rmc/compile_stderr.log
)

# Returns dict with:
# - rubric_10pt: {
#     syntax_correctness:  {score:0-1, max:1, method:"automated", detail:{...}},
#     attribute_coverage:  {score:0-3, max:3, method:"automated", detail:{...}},
#     actor_coverage:      {score:0-2, max:2, method:"automated", detail:{...}},
#     hallucination_free:  {score:0-1, max:1, method:"auto_partial", detail:{...}},
#     logic_correctness:   {score:0-2, max:2, method:"heuristic", detail:{...}},
#     total: 0-9, max: 9
#   }
# - score_breakdown: {base_10pt_pct, vacuity_pct, mutation_pct}
# - score_total: 0-100  (normalized; weights depend on which analyses ran)
# - status: Pass|Fail|Conditional|Blocked|Unknown
# - confidence: 0.0-1.0
# - vacuity: {is_vacuous, assertion_id, status}
# - failure_reasons: list
# - remediation_hints: list
#
# Normalization weights:
#   Neither vacuity nor mutation: base=100%
#   Vacuity only:  base=85%  + vacuity=15%
#   Mutation only: base=75%  + mutation=25%
#   Both:          base=60%  + vacuity=15% + mutation=25%
```

## API/CLI Contract Sync (auto-generated source of truth)

To avoid doc drift, regenerate and review the live API/CLI contract directly from scripts:

```bash
python3 - <<'PY'
import importlib
from pathlib import Path

scripts = Path("<scripts>")
exports = importlib.import_module("skills.rebeca_tooling.scripts").__all__
print("# Exported symbols")
for name in sorted(exports):
    print(f"- {name}")

print("\n# CLI modules")
for p in sorted(scripts.glob("*.py")):
    if p.name in {"__init__.py", "utils.py"}:
        continue
    print(f"- {p.name}")
PY
```

Policy: if this generated list differs from SKILL.md examples, update SKILL.md in the same change.

#### Generate Aggregate Report

```python
from scripts.generate_report import ReportGenerator

generator = ReportGenerator()
generator.add_scorecard(scorecard)
generator.finalize()

Path("reports/").mkdir(parents=True, exist_ok=True)
with open("reports/summary.json", "w") as f:
    f.write(generator.to_json())
with open("reports/summary.md", "w") as f:
    f.write(generator.to_markdown())

# Outputs: reports/summary.json and reports/summary.md
# Use generate_report.py --output-dir to also emit verification.json and quality_gates.json.
```

#### Generate Per-Rule Comprehensive Report

```python
from pathlib import Path
from scripts.reporting_metrics import build_rule_report_bundle
from scripts.generate_rule_report import _build_report_payload, _render_markdown

rule_dir = Path("output/rules/Rule-22")
bundle = build_rule_report_bundle(rule_dir)
payload = _build_report_payload(bundle)

out_dir = rule_dir / "reports"
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "comprehensive_report.json").write_text(
  __import__("json").dumps(payload, indent=2),
  encoding="utf-8",
)
(out_dir / "comprehensive_report.md").write_text(
  _render_markdown(payload),
  encoding="utf-8",
)
```

#### Consolidate Multiple Rule Folders

```python
from pathlib import Path
from scripts.reporting_metrics import build_rule_report_bundle

root = Path("output/rules")
bundles = []
for child in root.iterdir():
  if child.is_dir():
    try:
      bundles.append(build_rule_report_bundle(child))
    except FileNotFoundError:
      # skip folders that are not completed rule artifacts
      pass

print(f"Loaded {len(bundles)} rule bundles for consolidation")
```

## CLI Usage

For coordinator-invoked step CLIs, see **Direct Exec Step CLIs (Coordinator Reference)** in Module Reference below.

For general script usage, run any script with `--help`:

```bash
python3 <scripts>/run_rmc.py --help
python3 <scripts>/classify_rule_status.py --help
python3 <scripts>/verify_gate.py --help
python3 <scripts>/score_rule.py --help
python3 <scripts>/generate_report.py --help
```

## Platform Support

All modules work identically on:
- **Windows** (Python 3.8+ with g++/MinGW or WSL2)
- **macOS** (Python 3.8+ with Xcode Command Line Tools)
- **Linux** (Python 3.8+ with build-essential)

## Prerequisites

- Python 3.8+
- Java 11+ (for RMC)
- C++ compiler (g++ or clang, for RMC C++ compilation)

## Error Handling Pattern

```python
from scripts import run_rmc

def verify_rule(rule_id: str, model_path: str, property_path: str) -> dict:
    """Verify a single rule and return structured result."""
    output_dir = f"verification_output/{rule_id}"

    result = run_rmc(
        jar=".agents/rmc/rmc.jar",
        model=model_path,
        property_file=property_path,
        output_dir=output_dir,
        timeout_seconds=120
    )

    if result == 0:
        return {"rule_id": rule_id, "status": "verified"}
    elif result == 5:
        return {"rule_id": rule_id, "status": "syntax_error", "error_type": "rebeca_parse"}
    elif result == 4:
        return {"rule_id": rule_id, "status": "syntax_error", "error_type": "cpp_compile"}
    elif result == 3:
        return {"rule_id": rule_id, "status": "timeout"}
    else:
        return {"rule_id": rule_id, "status": "error", "exit_code": result}
```

## Module Reference

| Module | Purpose | CLI |
|--------|---------|-----|
| `run_rmc.py` | Execute RMC model checker | ✓ |
| `verify_gate.py` | Single-call gate: RMC → vacuity → mutation; outputs `passes_gate` | ✓ |
| `score_rule.py` | 100-point scoring rubric; `--rmc-exit-code`, `--is-vacuous`, `--mutation-score` | ✓ |
| `generate_report.py` | Aggregate report from scorecards; pipe from `score_rule.py` | ✓ |
| `output_policy.py` | Canonical path policy — the only permitted source of artifact paths | ✗ |
| `artifact_writer.py` | Atomically persist a step artifact (tmp→rename) | ✓ |

### Direct Exec Step CLIs (Coordinator Reference)

These CLIs are used by the coordinator for the deterministic pipeline steps.

#### `step05_verification_gate` (`verification_exec`) — RMC + vacuity + mutation

```bash
python3 <scripts>/verify_gate.py \
  --jar        <jar> \
  --model      <model_path> \
  --property   <property_path> \
  --rule-id    <rule_id> \
  --output-dir <verification_run_dir> \
  --output-file <verification_run_dir>/gate_result.json \
  --output-json
  # Optional: append --vacuity to enable vacuity checking (default: off)
  # Optional: append --mutation to enable mutation-based testing (default: off)
```

Key output fields in `gate_result.json`:

| Field                       | Meaning                                    |
|-----------------------------|--------------------------------------------|
| `passes_gate`               | `true` only when all three criteria met    |
| `rmc_exit_code`             | 0 = parse + compile OK                     |
| `vacuity_status.is_vacuous` | `true` = assertion trivially satisfied; `null` if vacuity was not enabled |
| `mutation_score`            | kill rate 0–100; threshold is 80; `null` if mutation was not enabled |

#### `step07_reporting` (`reporting_exec`) — Score and report

Three sequential commands. `score_rule.py` writes `step07_reporting.json`; `generate_report.py` reads it; `generate_rule_report.py` generates per-rule comprehensive report.

```bash
# Step 07a — Score (conditionally add --is-vacuous and --mutation-score)
python3 <scripts>/score_rule.py \
  --rule-id       <rule_id> \
  --rmc-exit-code <rmc_exit_code> \
  --output-dir    <output_dir> \
  $([ "<vacuity_status.is_vacuous>" != "null" ] && echo "--is-vacuous <true|false>" || true) \
  $([ "<mutation_score>" != "null" ] && echo "--mutation-score <mutation_score>" || true)

# Step 07b — Aggregate Report
python3 <scripts>/generate_report.py \
  --input-scores <output_dir>/work/<rule_id>/step07_reporting.json \
  --output-dir   <output_dir>/reports/<rule_id> \
  --format both

# Step 07c — Per-Rule Comprehensive Report
python3 <scripts>/generate_rule_report.py \
  --rule-dir   <output_dir>/<rule_id> \
  --output-dir <output_dir>/reports/<rule_id>
```

## JSON Output Purity Contract

For every script supporting `--output-json`:
- **stdout** must contain JSON only (no logs/progress text)
- human-readable diagnostics/progress belong on **stderr**
- this contract is regression-tested in `tests/test_json_purity_cli.py`

When chaining scripts in pipelines, prefer JSON-mode everywhere:

```bash
python3 <scripts>/classify_rule_status.py \
  --legata-path legata/Rule-22.legata \
  --output-json
```

## Docs/CLI Drift Guardrail

Use the sync validator before releasing doc changes:

```bash
python3 scripts/validate-cli-help-sync.py
```

CI also runs this automatically via `.github/workflows/cli-help-doc-sync.yml`.

## Best Practices

1. **Check exit codes** - Don't assume success, handle all error cases
3. **Use absolute paths** - Avoid relative paths for jar, model, and property files
4. **Set appropriate timeouts** - Complex models may need >120s
5. **Handle C++ compilation failures** - Exit code 4 means g++ failed, not RMC
6. **Distinguish parse vs compile errors** - Exit code 5 (parse) vs 4 (compile)
7. **Review fallback mappings** - COLREG fallback always requires manual review
8. **Feed vacuity result into score_rule** using `--is-vacuous` — read `vacuity_status.is_vacuous` from `verify_gate.py` output; a vacuous pass silently scores 100 otherwise
9. **Pipe scorecards as JSON array or NDJSON** to generate_report.py; do not rely on stdin line-by-line when cards span multiple lines
10. **Use generate_rule_report.py for artifact-rich per-rule outputs** instead of scorecard-only summaries when mutation/vacuity/model stats are required
11. **Use consolidate_reports.py for portfolio-level review** and include SVG plots for papers/decks, PNG for slides/CI artifacts

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `Invalid or corrupt jarfile` at JVM startup | Stale or partial download | Delete the jar and re-run `setup.py` to re-provision |
| `rmc_path.txt` not found | Path marker written with `.txt` extension by third-party tooling | Resolver now probes both `rmc_path` and `rmc_path.txt` |
| `JSONDecodeError` piping pretty JSON to `generate_report.py` | Old main() was line-by-line only | Use `--input-scores file.json` or pipe a JSON array / NDJSON; both now accepted |
| Reports overwrite root `output/report.*` on each run | Flat output path | `generate_report.py --output-dir output` now writes nested `output/reports/<rule-id>/report.{json,md}` (single rule) or `output/reports/aggregate/` (multi-rule) |
| Report shows `rules_passed: 0` despite per-rule data | `finalize()` was a no-op | Fixed — `finalize()` now recomputes all aggregate fields from `per_rule_scorecards` |

### Import Errors

If you get `ModuleNotFoundError`:
```python
# Ensure skill path is correct
skill_path = Path("<skills>/rebeca_tooling").expanduser()
print(f"Skill path exists: {skill_path.exists()}")
print(f"Scripts path exists: {(skill_path / 'scripts').exists()}")
```

### RMC Not Found

Re-run `setup.py` to provision RMC. It downloads the jar and writes the path marker automatically.

### C++ Compilation Failures

Exit code 4 means g++ failed. Check:
```bash
g++ --version  # Ensure g++ is installed
```

Install if missing:
- Ubuntu/Debian: `sudo apt install build-essential`
- macOS: `xcode-select --install`
- Windows: Install MinGW or use WSL2