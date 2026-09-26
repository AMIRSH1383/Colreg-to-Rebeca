#!/usr/bin/env python3
"""Validate documented CLI snippets against live --help output.

This check prevents docs drift by ensuring options used in documented
`python3 .../<script>.py ...` snippets are present in each script's current
`--help` output.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "skills" / "rebeca_tooling" / "scripts"
DEFAULT_DOC_FILES = (
    ROOT / "README.md",
    ROOT / "docs" / "skills" / "rebeca-tooling.md",
    ROOT / "docs" / "guides" / "troubleshooting.md",
    ROOT / "skills" / "rebeca_tooling" / "SKILL.md",
    ROOT / ".github" / "skills" / "rebeca_tooling" / "SKILL.md",
)


_SCRIPT_RE = re.compile(r"python3\s+[^\n`|]*?([A-Za-z_][A-Za-z0-9_]*)\.py\b")
_OPTION_RE = re.compile(r"--[A-Za-z0-9][A-Za-z0-9-]*")


def _extract_documented_script_options(doc_files: List[Path]) -> Dict[str, Set[str]]:
    """Return {script_name: {--option, ...}} from markdown command snippets."""
    result: Dict[str, Set[str]] = {}

    for doc_path in doc_files:
        if not doc_path.exists():
            continue
        text = doc_path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        for idx, line in enumerate(lines):
            script_match = _SCRIPT_RE.search(line)
            if script_match is None:
                continue

            script_name = script_match.group(1)
            script_path = SCRIPTS_DIR / f"{script_name}.py"
            if not script_path.exists():
                # Ignore snippets for external/unowned scripts.
                continue

            # Capture only the command line plus shell continuation lines.
            cmd_lines = [line]
            j = idx
            while cmd_lines[-1].rstrip().endswith("\\") and j + 1 < len(lines):
                j += 1
                cmd_lines.append(lines[j])
            snippet = "\n".join(cmd_lines)

            options = set(_OPTION_RE.findall(snippet))
            result.setdefault(script_name, set()).update(options)

    return result


def _run_help(script_path: Path) -> Tuple[int, str, str]:
    """Run `<script> --help` and return (returncode, stdout, stderr)."""
    proc = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def validate_cli_help_sync(doc_files: List[Path]) -> int:
    """Validate docs snippets options exist in live script help output."""
    documented = _extract_documented_script_options(doc_files)
    if not documented:
        print("ERROR: no documented rebeca_tooling script snippets found", file=sys.stderr)
        return 1

    failures = 0
    for script_name in sorted(documented):
        script_path = SCRIPTS_DIR / f"{script_name}.py"
        returncode, stdout, stderr = _run_help(script_path)

        if returncode != 0:
            failures += 1
            print(f"✗ {script_name}.py --help failed with code {returncode}", file=sys.stderr)
            if stderr.strip():
                print(stderr.strip(), file=sys.stderr)
            continue

        help_text = stdout
        missing = sorted(opt for opt in documented[script_name] if opt not in help_text)
        if missing:
            failures += 1
            print(
                f"✗ {script_name}.py docs/help drift: options in docs but missing from --help: {', '.join(missing)}",
                file=sys.stderr,
            )
        else:
            print(f"✓ {script_name}.py")

    if failures:
        print(f"\nFAIL: {failures} script(s) have docs/help drift", file=sys.stderr)
        return 1

    print("\nPASS: documented CLI snippets are in sync with --help output")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate documented rebeca_tooling CLI snippets against live --help output"
    )
    parser.add_argument(
        "--docs",
        nargs="*",
        default=[str(path) for path in DEFAULT_DOC_FILES],
        help="Optional explicit list of markdown files to scan",
    )
    args = parser.parse_args()

    doc_paths = [Path(p) for p in args.docs]
    sys.exit(validate_cli_help_sync(doc_paths))


if __name__ == "__main__":
    main()
