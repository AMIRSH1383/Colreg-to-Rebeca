#!/usr/bin/env python3
"""Atomic step artifact writer for the Legata→Rebeca pipeline.

Usage:
    python artifact_writer.py --rule-id RULE_ID --step STEP_NAME
        --data '{"status":"ok",...}' [--base-dir output]

Writes JSON to output/work/<rule_id>/<step>.json atomically (tmp→rename).
Exit 0 on success, 1 on failure.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Atomically write a step artifact JSON")
    parser.add_argument("--rule-id", required=True)
    parser.add_argument("--step", required=True, help="e.g. step02_abstraction")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--data", help="JSON string of artifact payload")
    group.add_argument("--from-file", metavar="PATH", help="Path to JSON file to read payload from")
    parser.add_argument("--base-dir", default="output")
    args = parser.parse_args()

    # Import output_policy from sibling directory
    sys.path.insert(0, str(Path(__file__).parent))
    from output_policy import step_artifact_path

    try:
        if args.from_file:
            raw = Path(args.from_file).read_text(encoding="utf-8")
        else:
            raw = args.data
        payload = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"status": "error", "message": f"Could not load artifact payload: {exc}"}))
        sys.exit(1)

    try:
        out_path = step_artifact_path(args.rule_id, args.step, Path(args.base_dir))
        _atomic_write(out_path, payload)
        print(json.dumps({"status": "ok", "path": str(out_path)}))
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
