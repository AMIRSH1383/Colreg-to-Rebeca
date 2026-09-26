"""Tests for shared rmc_resolver lookup behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from skills.rebeca_tooling.scripts.rmc_resolver import require_rmc_jar, resolve_rmc_jar


def _write_jar(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PK\x03\x04stub")


def test_resolve_rmc_jar_prefers_rmc_jar_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    explicit = tmp_path / "explicit" / "rmc.jar"
    fallback = tmp_path / "home" / ".claude" / "rmc" / "rmc.jar"
    _write_jar(explicit)
    _write_jar(fallback)

    monkeypatch.setenv("RMC_JAR", str(explicit))
    monkeypatch.delenv("RMC_DESTINATION", raising=False)
    monkeypatch.setattr("skills.rebeca_tooling.scripts.rmc_resolver.Path.home", lambda: tmp_path / "home")

    resolved = resolve_rmc_jar()
    assert resolved == str(explicit)


def test_resolve_rmc_jar_uses_rmc_destination_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    destination = tmp_path / "destination"
    jar = destination / "rmc.jar"
    _write_jar(jar)

    monkeypatch.delenv("RMC_JAR", raising=False)
    monkeypatch.setenv("RMC_DESTINATION", str(destination))

    resolved = resolve_rmc_jar()
    assert resolved == str(jar)


def test_resolve_rmc_jar_prefers_cwd_marker_over_home_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cwd_base = tmp_path / "cwd"
    home_base = tmp_path / "home"
    cwd_jar = tmp_path / "cand" / "cwd.jar"
    home_jar = tmp_path / "cand" / "home.jar"
    _write_jar(cwd_jar)
    _write_jar(home_jar)

    (cwd_base / ".claude").mkdir(parents=True, exist_ok=True)
    (home_base / ".claude").mkdir(parents=True, exist_ok=True)
    (cwd_base / ".claude" / "rmc_path").write_text(str(cwd_jar), encoding="utf-8")
    (home_base / ".claude" / "rmc_path").write_text(str(home_jar), encoding="utf-8")

    monkeypatch.delenv("RMC_JAR", raising=False)
    monkeypatch.delenv("RMC_DESTINATION", raising=False)
    monkeypatch.setattr("skills.rebeca_tooling.scripts.rmc_resolver.Path.cwd", lambda: cwd_base)
    monkeypatch.setattr("skills.rebeca_tooling.scripts.rmc_resolver.Path.home", lambda: home_base)

    resolved = resolve_rmc_jar()
    assert resolved == str(cwd_jar)


def test_resolve_rmc_jar_falls_back_to_home_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home_base = tmp_path / "home"
    fallback = home_base / ".claude" / "rmc" / "rmc.jar"
    _write_jar(fallback)

    monkeypatch.delenv("RMC_JAR", raising=False)
    monkeypatch.delenv("RMC_DESTINATION", raising=False)
    monkeypatch.setattr("skills.rebeca_tooling.scripts.rmc_resolver.Path.cwd", lambda: tmp_path / "cwd")
    monkeypatch.setattr("skills.rebeca_tooling.scripts.rmc_resolver.Path.home", lambda: home_base)

    resolved = resolve_rmc_jar()
    assert resolved == str(fallback)


def test_require_rmc_jar_error_includes_search_trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cwd_base = tmp_path / "cwd"
    home_base = tmp_path / "home"
    (cwd_base / ".claude").mkdir(parents=True, exist_ok=True)
    (home_base / ".claude").mkdir(parents=True, exist_ok=True)

    # Create an unreadable marker shape (directory) to ensure resolve_rmc_jar never raises.
    (cwd_base / ".claude" / "rmc_path").mkdir(parents=True, exist_ok=True)

    monkeypatch.delenv("RMC_JAR", raising=False)
    monkeypatch.delenv("RMC_DESTINATION", raising=False)
    monkeypatch.setattr("skills.rebeca_tooling.scripts.rmc_resolver.Path.cwd", lambda: cwd_base)
    monkeypatch.setattr("skills.rebeca_tooling.scripts.rmc_resolver.Path.home", lambda: home_base)

    assert resolve_rmc_jar() is None

    with pytest.raises(FileNotFoundError) as exc_info:
        require_rmc_jar()

    message = str(exc_info.value)
    assert "Unable to locate rmc.jar" in message
    assert str(home_base / ".claude" / "rmc" / "rmc.jar") in message
    assert str(cwd_base / ".claude" / "rmc_path") in message
