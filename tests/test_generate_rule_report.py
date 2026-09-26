"""Tests for generate_rule_report.py."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def test_generate_rule_report_creates_md_and_json() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        rule_dir = base / "rule23"
        (rule_dir / "model").mkdir(parents=True)
        (rule_dir / "property").mkdir(parents=True)

        (rule_dir / "scorecard_Rule-23.json").write_text(
            json.dumps(
                {
                    "rule_id": "Rule-23",
                    "status": "Conditional",
                    "score_total": 85,
                    "score_breakdown": {
                        "syntax": 10,
                        "semantic_alignment": 55,
                        "verification_outcome": 10,
                        "hallucination_penalty": 10,
                    },
                    "failure_reasons": [
                        "Property verified but vacuously — precondition is never reachable"
                    ],
                    "remediation_hints": ["Review precondition reachability"],
                }
            ),
            encoding="utf-8",
        )

        (rule_dir / "model" / "m.rebeca").write_text(
            "reactiveclass A(1){ statevars { int x; } } main { A a():(); }\n",
            encoding="utf-8",
        )
        (rule_dir / "property" / "p.property").write_text(
            "property { define { p=(a.x>0); } Assertion { Rule23: p; } }\n",
            encoding="utf-8",
        )

        script = Path(__file__).resolve().parents[1] / "skills" / "rebeca_tooling" / "scripts" / "generate_rule_report.py"
        proc = subprocess.run(
            [
                "python3",
                str(script),
                "--rule-dir",
                str(rule_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert proc.returncode == 0, proc.stderr
        report_dir = base / "reports" / "Rule-23"
        report_json = report_dir / "comprehensive_report.json"
        report_md = report_dir / "comprehensive_report.md"
        assert report_json.exists()
        assert report_md.exists()

        payload = json.loads(report_json.read_text(encoding="utf-8"))
        assert payload["rule_id"] == "Rule-23"
        assert payload["status"] == "Conditional"
        assert payload["metrics"]["model_property"]["statevars_count"] == 1
        md_text = report_md.read_text(encoding="utf-8")
        assert "Mutation Testing" in md_text
        assert "How to Interpret This Report" in md_text
        assert "Mutation Interpretation" in md_text
        assert "$100 \\times \\frac{\\text{killed}}{\\text{executed}}$" in md_text
        assert "Vacuity Interpretation" in md_text


def test_generate_rule_report_defaults_to_output_reports_when_rule_dir_is_packaged() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        rule_dir = base / "output" / "packaged" / "Rule-23"
        (rule_dir / "model").mkdir(parents=True)
        (rule_dir / "property").mkdir(parents=True)

        (rule_dir / "scorecard_Rule-23.json").write_text(
            json.dumps(
                {
                    "rule_id": "Rule-23",
                    "status": "Conditional",
                    "score_total": 85,
                    "score_breakdown": {"syntax": 10},
                }
            ),
            encoding="utf-8",
        )
        (rule_dir / "model" / "m.rebeca").write_text(
            "reactiveclass A(1){ statevars { int x; } } main { A a():(); }\n",
            encoding="utf-8",
        )
        (rule_dir / "property" / "p.property").write_text(
            "property { define { p=(a.x>0); } Assertion { Rule23: p; } }\n",
            encoding="utf-8",
        )

        script = Path(__file__).resolve().parents[1] / "skills" / "rebeca_tooling" / "scripts" / "generate_rule_report.py"
        proc = subprocess.run(
            [
                "python3",
                str(script),
                "--rule-dir",
                str(rule_dir),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert proc.returncode == 0, proc.stderr
        report_json = base / "output" / "reports" / "Rule-23" / "comprehensive_report.json"
        report_md = base / "output" / "reports" / "Rule-23" / "comprehensive_report.md"
        assert report_json.exists()
        assert report_md.exists()
