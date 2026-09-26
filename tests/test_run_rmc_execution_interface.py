"""Tests for run_rmc detailed execution interface and model.out args passthrough."""

from __future__ import annotations

import tempfile
from pathlib import Path

import run_rmc as run_rmc_module


def test_run_model_out_passes_args(monkeypatch) -> None:
    captured = {"cmd": None}

    class _Proc:
        returncode = 0

    def _run_stub(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr(run_rmc_module.subprocess, "run", _run_stub)

    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        exe = Path(td) / "model.out"
        exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        result = run_rmc_module.run_model_out(
            executable=exe,
            timeout_seconds=5,
            args=["--seed", "42"],
        )

    assert result["executed"] is True
    assert result["exit_code"] == 0
    assert captured["cmd"] == [str(exe), "--seed", "42"]


def test_run_model_out_supports_rmc_flags(monkeypatch) -> None:
    captured = {"cmd": None}

    class _Proc:
        returncode = 0

    def _run_stub(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr(run_rmc_module.subprocess, "run", _run_stub)

    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        exe = base / "model.out"
        exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        result = run_rmc_module.run_model_out(
            executable=exe,
            timeout_seconds=5,
            export_result="res.txt",
            hashmap_size=21,
            export_statespace="states.txt",
        )

    assert result["executed"] is True
    assert captured["cmd"] == [
        str(exe),
        "-o", str(exe.parent / "res.txt"),
        "-s", "21",
        "-x", str(exe.parent / "states.txt"),
    ]


def test_run_model_out_rejects_small_hashmap_size() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        exe = Path(td) / "model.out"
        exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

        result = run_rmc_module.run_model_out(
            executable=exe,
            timeout_seconds=5,
            hashmap_size=20,
        )

    assert result["executed"] is False
    assert "must be > 20" in str(result["error"])


def test_run_rmc_detailed_forwards_model_out_args(monkeypatch) -> None:
    calls = {"model_out_args": None}

    class _Proc:
        def __init__(self, returncode: int):
            self.returncode = returncode

    def _subprocess_stub(cmd, **kwargs):
        # java call: create one cpp artifact so parse phase passes
        if cmd and cmd[0] == "java":
            cwd = Path(kwargs["cwd"])
            (cwd / "generated.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
            return _Proc(0)
        # g++ call: create expected executable
        if cmd and cmd[0] == "g++":
            exe_path = Path(cmd[-1])
            exe_path.write_text("binary", encoding="utf-8")
            return _Proc(0)
        return _Proc(0)

    def _model_out_stub(executable, timeout_seconds=30, args=None, **kwargs):
        calls["model_out_args"] = list(args or [])
        return {
            "executed": True,
            "exit_code": 0,
            "outcome": "satisfied",
            "error": None,
        }

    monkeypatch.setattr(run_rmc_module.subprocess, "run", _subprocess_stub)
    monkeypatch.setattr(run_rmc_module, "run_model_out", _model_out_stub)

    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        jar = base / "rmc.jar"
        model = base / "m.rebeca"
        prop = base / "p.property"
        out = base / "out"

        jar.write_text("jar", encoding="utf-8")
        model.write_text("reactiveclass A(1) {} main { A a():(); }\n", encoding="utf-8")
        prop.write_text("property { Assertion { R: true; } }\n", encoding="utf-8")

        details = run_rmc_module.run_rmc_detailed(
            jar=str(jar),
            model=str(model),
            property_file=str(prop),
            output_dir=str(out),
            run_model_outcome=True,
            model_out_args=["--steps", "10"],
        )

    assert details["rmc_exit_code"] == 0
    assert details["verification_outcome"] == "satisfied"
    assert calls["model_out_args"] == ["--steps", "10"]


def test_run_rmc_detailed_forwards_model_out_named_flags(monkeypatch) -> None:
    calls = {
        "model_out_args": None,
        "export_result": None,
        "hashmap_size": None,
        "export_statespace": None,
    }

    class _Proc:
        def __init__(self, returncode: int):
            self.returncode = returncode

    def _subprocess_stub(cmd, **kwargs):
        if cmd and cmd[0] == "java":
            cwd = Path(kwargs["cwd"])
            (cwd / "generated.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
            return _Proc(0)
        if cmd and cmd[0] == "g++":
            exe_path = Path(cmd[-1])
            exe_path.write_text("binary", encoding="utf-8")
            return _Proc(0)
        return _Proc(0)

    def _model_out_stub(executable, timeout_seconds=30, args=None, export_result=None,
                        hashmap_size=None, export_statespace=None):
        calls["model_out_args"] = list(args or [])
        calls["export_result"] = export_result
        calls["hashmap_size"] = hashmap_size
        calls["export_statespace"] = export_statespace
        return {
            "executed": True,
            "exit_code": 0,
            "outcome": "satisfied",
            "error": None,
        }

    monkeypatch.setattr(run_rmc_module.subprocess, "run", _subprocess_stub)
    monkeypatch.setattr(run_rmc_module, "run_model_out", _model_out_stub)

    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        jar = base / "rmc.jar"
        model = base / "m.rebeca"
        prop = base / "p.property"
        out = base / "out"

        jar.write_text("jar", encoding="utf-8")
        model.write_text("reactiveclass A(1) {} main { A a():(); }\n", encoding="utf-8")
        prop.write_text("property { Assertion { R: true; } }\n", encoding="utf-8")

        details = run_rmc_module.run_rmc_detailed(
            jar=str(jar),
            model=str(model),
            property_file=str(prop),
            output_dir=str(out),
            run_model_outcome=True,
            model_out_args=["--steps", "10"],
            model_out_export_result="res.txt",
            model_out_hashmap_size=21,
            model_out_export_statespace="states.txt",
        )

    assert details["rmc_exit_code"] == 0
    assert details["verification_outcome"] == "satisfied"
    assert calls["model_out_args"] == ["--steps", "10"]
    assert calls["export_result"] == "res.txt"
    assert calls["hashmap_size"] == 21
    assert calls["export_statespace"] == "states.txt"


def test_run_rmc_detailed_uses_result_artifact_when_model_out_unknown(monkeypatch) -> None:
    class _Proc:
        def __init__(self, returncode: int):
            self.returncode = returncode

    def _subprocess_stub(cmd, **kwargs):
        if cmd and cmd[0] == "java":
            cwd = Path(kwargs["cwd"])
            (cwd / "generated.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
            return _Proc(0)
        if cmd and cmd[0] == "g++":
            exe_path = Path(cmd[-1])
            exe_path.write_text("binary", encoding="utf-8")
            return _Proc(0)
        return _Proc(0)

    def _model_out_stub(executable, timeout_seconds=30, args=None, **kwargs):
        return {
            "executed": False,
            "exit_code": None,
            "outcome": "unknown",
            "error": "simulated unknown outcome",
        }

    def _parse_stub(result_path):
        return {
            "path": result_path,
            "exists": True,
            "parsed": True,
            "format": "xml",
            "outcome": "cex",
            "error": None,
        }

    monkeypatch.setattr(run_rmc_module.subprocess, "run", _subprocess_stub)
    monkeypatch.setattr(run_rmc_module, "run_model_out", _model_out_stub)
    monkeypatch.setattr(run_rmc_module, "parse_rmc_result_file", _parse_stub)

    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        jar = base / "rmc.jar"
        model = base / "m.rebeca"
        prop = base / "p.property"
        out = base / "out"

        jar.write_text("jar", encoding="utf-8")
        model.write_text("reactiveclass A(1) {} main { A a():(); }\n", encoding="utf-8")
        prop.write_text("property { Assertion { R: true; } }\n", encoding="utf-8")

        details = run_rmc_module.run_rmc_detailed(
            jar=str(jar),
            model=str(model),
            property_file=str(prop),
            output_dir=str(out),
            run_model_outcome=True,
            model_out_export_result="result.xml",
        )

    assert details["rmc_exit_code"] == 0
    assert details["verification_outcome"] == "cex"
    assert details["result_artifact"]["parsed"] is True
    assert details["result_artifact"]["outcome"] == "cex"


def test_run_rmc_detailed_prefers_result_artifact_over_model_out_exit_outcome(monkeypatch) -> None:
    class _Proc:
        def __init__(self, returncode: int):
            self.returncode = returncode

    def _subprocess_stub(cmd, **kwargs):
        if cmd and cmd[0] == "java":
            cwd = Path(kwargs["cwd"])
            (cwd / "generated.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
            return _Proc(0)
        if cmd and cmd[0] == "g++":
            exe_path = Path(cmd[-1])
            exe_path.write_text("binary", encoding="utf-8")
            return _Proc(0)
        return _Proc(0)

    def _model_out_stub(executable, timeout_seconds=30, args=None, **kwargs):
        return {
            "executed": True,
            "exit_code": 0,
            "outcome": "satisfied",
            "error": None,
        }

    def _parse_stub(result_path):
        return {
            "path": result_path,
            "exists": True,
            "parsed": True,
            "format": "xml",
            "outcome": "cex",
            "error": None,
        }

    monkeypatch.setattr(run_rmc_module.subprocess, "run", _subprocess_stub)
    monkeypatch.setattr(run_rmc_module, "run_model_out", _model_out_stub)
    monkeypatch.setattr(run_rmc_module, "parse_rmc_result_file", _parse_stub)

    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        base = Path(td)
        jar = base / "rmc.jar"
        model = base / "m.rebeca"
        prop = base / "p.property"
        out = base / "out"

        jar.write_text("jar", encoding="utf-8")
        model.write_text("reactiveclass A(1) {} main { A a():(); }\n", encoding="utf-8")
        prop.write_text("property { Assertion { R: true; } }\n", encoding="utf-8")

        details = run_rmc_module.run_rmc_detailed(
            jar=str(jar),
            model=str(model),
            property_file=str(prop),
            output_dir=str(out),
            run_model_outcome=True,
            model_out_export_result="result.xml",
        )

    assert details["rmc_exit_code"] == 0
    assert details["verification_outcome"] == "cex"
