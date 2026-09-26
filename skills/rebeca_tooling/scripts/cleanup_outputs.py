#!/usr/bin/env python3
"""
Pipeline output cleanup utility.

Removes scratch work directories under ``output/work/<rule_id>/`` while
preserving promoted finals (``output/<rule_id>/``) and reports
(``output/reports/<rule_id>/``).

Usage examples
--------------
  # Remove ALL work dirs for one rule, keep latest verification run
  cleanup_outputs.py --rule-id COLREG-Rule22 --keep-latest

  # Wipe entire work tree for a rule (post-release housekeeping)
  cleanup_outputs.py --rule-id COLREG-Rule22

  # Dry-run to see what would be deleted
  cleanup_outputs.py --rule-id COLREG-Rule22 --dry-run

  # Clean across all rules under a non-default base
  cleanup_outputs.py --base-dir /tmp/pipeline-out --all-rules
"""

import argparse
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from output_policy import _validate_rule_id
from utils import safe_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_run_dirs(work_rule_dir: Path) -> List[Path]:
    """Return run subdirectories under work/<rule_id>/runs/, sorted by name."""
    runs_root = work_rule_dir / "runs"
    if not runs_root.is_dir():
        return []
    return sorted(p for p in runs_root.iterdir() if p.is_dir())


def _delete_dir(path: Path, dry_run: bool) -> Tuple[bool, str]:
    """
    Delete *path* recursively.

    Returns:
        ``(deleted: bool, message: str)``
    """
    if dry_run:
        return True, f"[dry-run] would delete: {path}"
    try:
        shutil.rmtree(path)
        return True, f"deleted: {path}"
    except Exception as exc:
        return False, f"error deleting {path}: {exc}"


# ---------------------------------------------------------------------------
# Core cleanup logic
# ---------------------------------------------------------------------------

def cleanup_rule(
    rule_id: str,
    base_dir: Path,
    keep_latest: bool = False,
    dry_run: bool = False,
) -> int:
    """
    Clean work/candidate directories for *rule_id*.

    Args:
        rule_id:     Rule identifier (validated against path-traversal).
        base_dir:    Root output directory (must already exist).
        keep_latest: When True, retain the most-recently-created run directory
                     under ``work/<rule_id>/runs/`` and skip the candidates dir
                     only if it is empty.
        dry_run:     Print what would be deleted without actually deleting.

    Returns:
        Number of directories deleted (or that *would* be deleted in dry-run).
    """
    _validate_rule_id(rule_id)
    work_rule_dir = safe_path(str(base_dir / "work" / rule_id))

    if not work_rule_dir.exists():
        print(f"Nothing to clean for rule {rule_id!r} (work dir not found: {work_rule_dir})")
        return 0

    deleted = 0

    # --- candidates dir ---
    candidates_dir = work_rule_dir / "candidates"
    if candidates_dir.is_dir():
        if keep_latest and any(candidates_dir.iterdir()):
            print(f"  kept (keep-latest, non-empty): {candidates_dir}")
        else:
            ok, msg = _delete_dir(candidates_dir, dry_run)
            print(f"  {msg}")
            if ok:
                deleted += 1

    # --- run dirs ---
    run_dirs = _list_run_dirs(work_rule_dir)
    if keep_latest and run_dirs:
        to_delete = run_dirs[:-1]          # keep the last (lexicographically greatest)
        kept = run_dirs[-1]
        print(f"  kept (keep-latest): {kept}")
    else:
        to_delete = run_dirs

    for run_dir in to_delete:
        ok, msg = _delete_dir(run_dir, dry_run)
        print(f"  {msg}")
        if ok:
            deleted += 1

    # Remove the runs/ container if now empty (and not dry_run)
    runs_root = work_rule_dir / "runs"
    if not dry_run and runs_root.is_dir() and not any(runs_root.iterdir()):
        try:
            runs_root.rmdir()
        except OSError:
            pass  # non-empty or race; ignore

    # Remove work/<rule_id>/ itself if now empty
    if not dry_run and work_rule_dir.is_dir() and not any(work_rule_dir.iterdir()):
        try:
            work_rule_dir.rmdir()
        except OSError:
            pass

    return deleted


def cleanup_all_rules(
    base_dir: Path,
    keep_latest: bool = False,
    dry_run: bool = False,
) -> int:
    """
    Run :func:`cleanup_rule` for every rule found under ``output/work/``.

    Returns total directories deleted.
    """
    work_root = base_dir / "work"
    if not work_root.is_dir():
        print(f"No work directory found at {work_root}")
        return 0

    total = 0
    for rule_dir in sorted(p for p in work_root.iterdir() if p.is_dir()):
        rule_id = rule_dir.name
        print(f"Rule: {rule_id}")
        total += cleanup_rule(rule_id, base_dir, keep_latest=keep_latest, dry_run=dry_run)

    return total


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean pipeline scratch/work directories without touching promoted finals or reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--rule-id", help="Rule identifier to clean (e.g. COLREG-Rule22)")
    target.add_argument("--all-rules", action="store_true", help="Clean all rules under base-dir")

    parser.add_argument(
        "--base-dir",
        default="output",
        help="Root output directory (default: output)",
    )
    parser.add_argument(
        "--keep-latest",
        action="store_true",
        help="Retain the most-recently-modified run directory and non-empty candidates dir",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be deleted without removing anything",
    )

    args = parser.parse_args()
    base_dir = safe_path(args.base_dir)

    if args.dry_run:
        print("[DRY RUN — no files will be deleted]")

    if args.all_rules:
        total = cleanup_all_rules(base_dir, keep_latest=args.keep_latest, dry_run=args.dry_run)
    else:
        try:
            _validate_rule_id(args.rule_id)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Rule: {args.rule_id}")
        total = cleanup_rule(args.rule_id, base_dir, keep_latest=args.keep_latest, dry_run=args.dry_run)

    suffix = " (dry-run)" if args.dry_run else ""
    print(f"\nTotal directories removed{suffix}: {total}")


if __name__ == "__main__":
    main()
