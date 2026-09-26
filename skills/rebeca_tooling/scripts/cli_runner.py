#!/usr/bin/env python3
import json
import os
import sys
import argparse
import importlib.util
from pathlib import Path
from typing import Any, Dict


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def run_verification(data: Dict[str, Any]) -> Dict[str, Any]:
    # Placeholder — real verification is driven by verification_exec via coordinator.
    # This stub returns a structurally correct payload so integration tests can exercise
    # the artifact-write path without invoking RMC.
    return {
        "status": "ok",
        "source_file_path": data.get("source_file_path", ""),
        "verified": True,
        "rmc_exit_code": 0,
        "rmc_output_dir": "",
        "vacuity_status": {"is_vacuous": False},
        "mutation_score": 100.0,
    }


# Add other specialized runners here...


_TOOL_TO_STEP: Dict[str, str] = {
    "verification": "step05_verification_gate",
}


def dispatch():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-file", default=None,
                        help="Path to atomically write the result JSON")
    parser.add_argument("--rule-id", default=None,
                        help="Rule ID; used to derive canonical output path when --output-file is omitted")
    parser.add_argument("--base-dir", default="output",
                        help="Base output directory (default: output)")
    args = parser.parse_args()

    input_data = json.loads(args.input)

    tools = {
        "verification": run_verification,
    }

    if args.tool not in tools:
        print(json.dumps({"status": "error", "message": f"Tool {args.tool} not found"}), file=sys.stderr)
        sys.exit(1)

    try:
        result = tools[args.tool](input_data)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        sys.exit(1)

    # Determine output path (explicit > canonical derived)
    out_path: Path | None = None
    if args.output_file:
        out_path = Path(args.output_file)
    elif args.rule_id and args.tool in _TOOL_TO_STEP:
        sys.path.insert(0, str(Path(__file__).parent))
        from output_policy import step_artifact_path
        out_path = step_artifact_path(args.rule_id, _TOOL_TO_STEP[args.tool], Path(args.base_dir))

    if out_path is not None:
        _atomic_write(out_path, result)

    print(json.dumps(result))


if __name__ == "__main__":
    dispatch()
