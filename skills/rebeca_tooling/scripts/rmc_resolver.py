#!/usr/bin/env python3
"""Shared RMC jar path resolution helpers.

This module centralizes where ``rmc.jar`` is discovered from, so all scripts
can use identical lookup behavior across local and global installs.
"""

from __future__ import annotations

import os
from pathlib import Path

# Canonical marker names accepted on read.
_MARKER_NAMES: tuple[str, str] = ("rmc_path", "rmc_path.txt")


def _candidate_bases() -> tuple[Path, Path]:
    """Return marker search bases in precedence order."""
    return (Path.cwd() / ".claude", Path.home() / ".claude")


def _read_marker(marker: Path) -> str | None:
    """Return marker payload or ``None`` for unreadable/empty marker files."""
    try:
        payload = marker.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    return payload or None


def _candidate_jars_with_trace() -> tuple[list[Path], list[str]]:
    """Build ordered candidate jar paths.

    Precedence:
      1. ``RMC_JAR``
      2. ``RMC_DESTINATION`` + ``rmc.jar``
      3. marker files under ``./.claude`` then ``~/.claude``
      4. fallback ``~/.claude/rmc/rmc.jar``
    """
    if os.environ.get("RMC_JAR"):
        jar = Path(os.environ["RMC_JAR"]).expanduser()
        return [jar], [f"RMC_JAR={jar}"]

    if os.environ.get("RMC_DESTINATION"):
        destination = Path(os.environ["RMC_DESTINATION"]).expanduser()
        candidate = destination / "rmc.jar"
        return [candidate], [f"RMC_DESTINATION={destination}", f"candidate={candidate}"]

    from_markers: list[Path] = []
    trace: list[str] = []
    for base in _candidate_bases():
        for marker_name in _MARKER_NAMES:
            marker_path = base / marker_name
            trace.append(f"marker={marker_path}")
            if not marker_path.exists():
                continue
            marker_payload = _read_marker(marker_path)
            if marker_payload:
                resolved = Path(marker_payload).expanduser()
                from_markers.append(resolved)
                trace.append(f"marker_value={resolved}")
            else:
                trace.append(f"marker_unreadable_or_empty={marker_path}")

    if from_markers:
        return from_markers, trace

    fallback = Path.home() / ".claude" / "rmc" / "rmc.jar"
    trace.append(f"fallback={fallback}")
    return [fallback], trace


def resolve_rmc_jar(*, must_exist: bool = True) -> str | None:
    """Resolve an ``rmc.jar`` path.

    Never raises. Returns ``None`` when ``must_exist=True`` and no candidate
    currently exists on disk.
    """
    try:
        candidates, _ = _candidate_jars_with_trace()
        if not candidates:
            return None
        if not must_exist:
            return str(candidates[0])

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        return None
    except Exception:
        return None


def require_rmc_jar() -> str:
    """Return an existing ``rmc.jar`` path or raise ``FileNotFoundError``.

    The raised message includes the full ordered search list for diagnostics.
    """
    resolved = resolve_rmc_jar(must_exist=True)
    if resolved:
        return resolved

    searched, trace = _candidate_jars_with_trace()
    details = "\n".join(f"- {entry}" for entry in [*(str(p) for p in searched), *trace])
    raise FileNotFoundError(
        "Unable to locate rmc.jar. Searched paths (in order):\n"
        f"{details}"
    )
