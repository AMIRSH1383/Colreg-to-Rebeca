#!/usr/bin/env python3
"""
validate-tooling.py

CI linting suite for skills/rebeca_tooling/scripts/.
Runs mypy --strict and flake8 --select=E,F,W on every .py file in the scripts
directory. Reports all violations and exits non-zero if any check fails.

Usage:
    python3 scripts/validate-tooling.py
    python3 scripts/validate-tooling.py --scripts-dir path/to/scripts
    python3 scripts/validate-tooling.py --mypy-only
    python3 scripts/validate-tooling.py --flake8-only
"""

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


_DEFAULT_SCRIPTS = (
    Path(__file__).parent.parent / "skills" / "rebeca_tooling" / "scripts"
)


def _run(cmd: List[str], label: str) -> Tuple[int, str]:
    """Run a subprocess and return (returncode, combined output)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode, output
    except FileNotFoundError:
        return 127, f"{label}: command not found — is it installed? ({cmd[0]})"


def run_mypy(scripts_dir: Path) -> Tuple[bool, str]:
    """Run mypy --strict on the scripts directory."""
    rc, output = _run(
        [
            "python3", "-m", "mypy",
            "--strict",
            "--ignore-missing-imports",
            "--no-error-summary",
            str(scripts_dir),
        ],
        "mypy",
    )
    passed = rc == 0
    return passed, output


def run_flake8(scripts_dir: Path) -> Tuple[bool, str]:
    """Run flake8 --select=E,F,W on the scripts directory."""
    rc, output = _run(
        [
            "python3", "-m", "flake8",
            "--select=E,F,W",
            "--max-line-length=100",
            # Ignore E501 (line too long) in schema path strings — they're non-negotiable
            "--extend-ignore=E501",
            str(scripts_dir),
        ],
        "flake8",
    )
    passed = rc == 0
    return passed, output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="validate-tooling: mypy + flake8 linting suite for rebeca_tooling scripts"
    )
    parser.add_argument(
        "--scripts-dir", default=str(_DEFAULT_SCRIPTS),
        help="Path to scripts directory (default: skills/rebeca_tooling/scripts/)",
    )
    parser.add_argument("--mypy-only",   action="store_true", help="Run only mypy")
    parser.add_argument("--flake8-only", action="store_true", help="Run only flake8")

    args = parser.parse_args()
    scripts_dir = Path(args.scripts_dir)

    if not scripts_dir.exists():
        print(f"ERROR: scripts-dir not found: {scripts_dir}", file=sys.stderr)
        sys.exit(1)

    run_mypy_check   = not args.flake8_only
    run_flake8_check = not args.mypy_only

    results: List[Tuple[str, bool, str]] = []

    if run_mypy_check:
        print(f"── mypy --strict {scripts_dir} ──")
        passed, output = run_mypy(scripts_dir)
        if output:
            print(output)
        status = "PASS" if passed else "FAIL"
        print(f"mypy: {status}\n")
        results.append(("mypy", passed, output))

    if run_flake8_check:
        print(f"── flake8 --select=E,F,W {scripts_dir} ──")
        passed, output = run_flake8(scripts_dir)
        if output:
            print(output)
        status = "PASS" if passed else "FAIL"
        print(f"flake8: {status}\n")
        results.append(("flake8", passed, output))

    all_passed = all(passed for _, passed, _ in results)

    print("── Summary ──")
    for tool, passed, _ in results:
        print(f"  {tool}: {'✓ PASS' if passed else '✗ FAIL'}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
