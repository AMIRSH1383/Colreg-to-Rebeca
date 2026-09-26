"""Path-layout tests for generate_report.py."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "skills" / "rebeca_tooling" / "scripts"


def test_generate_report_writes_single_rule_under_reports_rule_id() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        out = base / "output"

        scorecard = {
            "rule_id": "Rule-22",
            "status": "Pass",
            "score_total": 100,
            "score_breakdown": {
                "syntax": 10,
                "semantic_alignment": 55,
                "verification_outcome": 25,
                "hallucination_penalty": 10,
            },
        }

        proc = subprocess.run(
            [
                "python3",
                str(SCRIPTS_DIR / "generate_report.py"),
                "--input-scores",
                json.dumps([scorecard]),
                "--output-dir",
                str(out),
                "--format",
                "both",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert proc.returncode == 0, proc.stderr
        assert (out / "reports" / "Rule-22" / "summary.json").exists()
        assert (out / "reports" / "Rule-22" / "summary.md").exists()
        assert (out / "reports" / "Rule-22" / "verification.json").exists()
        assert (out / "reports" / "Rule-22" / "quality_gates.json").exists()


def test_generate_report_writes_multi_rule_under_reports_aggregate() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        out = base / "output"

        cards = [
            {"rule_id": "Rule-22", "status": "Pass", "score_total": 100, "score_breakdown": {}},
            {"rule_id": "Rule-23", "status": "Fail", "score_total": 40, "score_breakdown": {}},
        ]

        proc = subprocess.run(
            [
                "python3",
                str(SCRIPTS_DIR / "generate_report.py"),
                "--input-scores",
                json.dumps(cards),
                "--output-dir",
                str(out),
                "--format",
                "both",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert proc.returncode == 0, proc.stderr
        assert (out / "reports" / "aggregate" / "summary.json").exists()
        assert (out / "reports" / "aggregate" / "summary.md").exists()
        assert (out / "reports" / "aggregate" / "verification.json").exists()
        assert (out / "reports" / "aggregate" / "quality_gates.json").exists()


def test_generate_report_without_output_dir_still_writes_default_artifacts() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        scorecard = {
            "rule_id": "Rule-22",
            "status": "Pass",
            "score_total": 100,
            "score_breakdown": {"syntax": 10},
        }

        proc = subprocess.run(
            [
                "python3",
                str(SCRIPTS_DIR / "generate_report.py"),
                "--input-scores",
                json.dumps([scorecard]),
            ],
            cwd=str(base),
            capture_output=True,
            text=True,
            check=False,
        )

        assert proc.returncode == 0, proc.stderr
        # Stdout compatibility preserved (JSON emitted).
        payload = json.loads(proc.stdout)
        assert payload["total_rules"] == 1

        # Deterministic default artifact location.
        assert (base / "output" / "reports" / "Rule-22" / "summary.json").exists()
        assert (base / "output" / "reports" / "Rule-22" / "summary.md").exists()
        assert (base / "output" / "reports" / "Rule-22" / "verification.json").exists()
        assert (base / "output" / "reports" / "Rule-22" / "quality_gates.json").exists()
