"""Tests for consolidate_reports.py."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def _write_rule(rule_dir: Path, rule_id: str, status: str, score: int) -> None:
    (rule_dir / "scorecard.json").write_text(
        json.dumps(
            {
                "rule_id": rule_id,
                "status": status,
                "score_total": score,
                "score_breakdown": {
                    "syntax": 10,
                    "semantic_alignment": 55,
                    "verification_outcome": 10,
                    "hallucination_penalty": 10,
                },
                "failure_reasons": ["demo"],
                "remediation_hints": ["fix"],
            }
        ),
        encoding="utf-8",
    )
    (rule_dir / "mutation_candidates.json").write_text(
        json.dumps({"total_mutants": 20}), encoding="utf-8"
    )
    (rule_dir / "mutation_killrun.json").write_text(
        json.dumps(
            {
                "kill_stats": {
                    "total_generated": 10,
                    "total_run": 10,
                    "killed": 3,
                    "survived": 6,
                    "errors": 1,
                    "mutation_score": 30.0,
                }
            }
        ),
        encoding="utf-8",
    )
    (rule_dir / "model").mkdir(parents=True)
    (rule_dir / "property").mkdir(parents=True)
    (rule_dir / "model" / "m.rebeca").write_text(
        "reactiveclass A(1){ statevars { int x; int y; } } main { A a():(); }\n",
        encoding="utf-8",
    )
    (rule_dir / "property" / "p.property").write_text(
        "property { define { p=(a.x>0); q=(a.y>0);} Assertion { A1: p; A2:q;} }\n",
        encoding="utf-8",
    )


def test_consolidate_reports_generates_outputs_without_plots() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        root = base / "output"
        out = base / "consolidated"
        rule_a = root / "rule22"
        rule_b = root / "rule23"
        rule_a.mkdir(parents=True)
        rule_b.mkdir(parents=True)

        _write_rule(rule_a, "Rule-22", "Conditional", 85)
        _write_rule(rule_b, "Rule-23", "Pass", 95)

        script = Path(__file__).resolve().parents[1] / "skills" / "rebeca_tooling" / "scripts" / "consolidate_reports.py"
        proc = subprocess.run(
            [
                "python3",
                str(script),
                "--root-output-dir",
                str(root),
                "--output-dir",
                str(out),
                "--skip-plots",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert proc.returncode == 0, proc.stderr
        report_json = out / "consolidated_report.json"
        report_md = out / "consolidated_report.md"
        assert report_json.exists()
        assert report_md.exists()

        payload = json.loads(report_json.read_text(encoding="utf-8"))
        assert payload["summary"]["total_rules"] == 2
        assert payload["status_counts"]["Pass"] == 1
        assert payload["status_counts"]["Conditional"] == 1
        assert payload["mutation_stats"]["mutants_generated_total"] == 40
        assert payload["plots"] == {}
