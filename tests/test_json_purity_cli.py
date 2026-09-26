"""Regression tests: --output-json must keep stdout parseable JSON."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPTS_DIR = Path(__file__).parent.parent / "skills" / "rebeca_tooling" / "scripts"


def _run_script(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable] + args,
        cwd=str(SCRIPTS_DIR),
        capture_output=True,
        text=True,
    )


def test_score_rule_output_json_stdout_is_pure_json() -> None:
    result = _run_script(
        [
            "score_rule.py",
            "--rule-id",
            "Rule-22",
            "--verify-status",
            "unknown",
            "--output-json",
        ]
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["rule_id"] == "Rule-22"


def test_classify_rule_status_output_json_stdout_is_pure_json() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        legata = Path(td) / "rule.legata"
        legata.write_text("TODO", encoding="utf-8")

        result = _run_script(
            [
                "classify_rule_status.py",
                "--legata-path",
                str(legata),
                "--output-json",
            ]
        )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert "status" in payload


def test_snapshotter_output_json_stdout_is_pure_json() -> None:
    model_text = "reactiveclass A(1) { statevars { int x; } A() { x = 0; } } main { A a():(); }"
    prop_text = "property { Assertion { Rule22: x >= 0; } }"

    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        model = base / "model.rebeca"
        prop = base / "model.property"
        out = base / "snapshot.json"
        model.write_text(model_text, encoding="utf-8")
        prop.write_text(prop_text, encoding="utf-8")

        result = _run_script(
            [
                "snapshotter.py",
                "--rule-id",
                "Rule-22",
                "--model",
                str(model),
                "--property",
                str(prop),
                "--output",
                str(out),
                "--output-json",
            ]
        )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["rule_id"] == "Rule-22"



def test_vacuity_checker_output_json_stdout_is_pure_json_on_error() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        model = base / "model.rebeca"
        jar = base / "rmc.jar"
        missing_prop = base / "missing.property"

        model.write_text("reactiveclass A(1) {} main { A a():(); }", encoding="utf-8")
        jar.write_text("jar", encoding="utf-8")

        result = _run_script(
            [
                "vacuity_checker.py",
                "--jar",
                str(jar),
                "--model",
                str(model),
                "--property",
                str(missing_prop),
                "--output-dir",
                str(base / "out"),
                "--output-json",
            ]
        )

    # Missing property is expected to exit non-zero, but stdout must remain JSON.
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["is_vacuous"] is None
    assert "not found" in payload["explanation"]


def test_mutation_engine_output_json_stdout_is_pure_json() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        model = base / "model.rebeca"
        prop = base / "model.property"

        model.write_text(
            "reactiveclass A(1) { statevars { int x; } msgsrv m() { x = x + 1; } } main { A a():(); }",
            encoding="utf-8",
        )
        prop.write_text(
            "property { define { isGood = (a.x > 0); } Assertion { Rule22: isGood; } }",
            encoding="utf-8",
        )

        result = _run_script(
            [
                "mutation_engine.py",
                "--rule-id",
                "Rule-22",
                "--model",
                str(model),
                "--property",
                str(prop),
                "--output-json",
            ]
        )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["rule_id"] == "Rule-22"
    assert "mutants" in payload
