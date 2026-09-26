#!/usr/bin/env python3
"""Execute RMC model checker with model and property files."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from rmc_result_parser import parse_rmc_result_file
from utils import safe_path


def _write_json_artifact(output_file: Path, payload: Dict[str, Any]) -> None:
    """Atomically write *payload* as UTF-8 JSON to *output_file* (temp + rename)."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    serialised = json.dumps(payload, indent=2, ensure_ascii=False)
    fd, tmp_path = tempfile.mkstemp(
        dir=output_file.parent,
        prefix=f".{output_file.name}.tmp",
        suffix=".json",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(serialised)
        os.replace(tmp_path, output_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _classify_model_outcome(exit_code: Optional[int]) -> str:
    """Map executable exit code to semantic outcome label."""
    if exit_code is None:
        return "unknown"
    return "satisfied" if exit_code == 0 else "cex"


def run_model_out(
    executable: Path,
    timeout_seconds: int = 30,
    args: Optional[List[str]] = None,
    export_result: Optional[str] = None,
    hashmap_size: Optional[int] = None,
    export_statespace: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute compiled `model.out` and capture semantic outcome details."""
    try:
        exe = safe_path(str(executable))
    except SystemExit:
        return {
            "executed": False,
            "exit_code": None,
            "outcome": "unknown",
            "error": f"Invalid executable path: {executable}",
        }

    if not exe.exists() or not exe.is_file():
        return {
            "executed": False,
            "exit_code": None,
            "outcome": "unknown",
            "error": f"Executable not found: {exe}",
        }

    if hashmap_size is not None and hashmap_size <= 20:
        return {
            "executed": False,
            "exit_code": None,
            "outcome": "unknown",
            "error": "Invalid --hashmapSize value: must be > 20",
        }

    try:
        cmd = [str(exe)]

        if export_result:
            out_file = Path(export_result)
            if not out_file.is_absolute():
                out_file = exe.parent / out_file
            out_file = safe_path(str(out_file))
            cmd.extend(["-o", str(out_file)])

        if hashmap_size is not None:
            cmd.extend(["-s", str(hashmap_size)])

        if export_statespace:
            statespace_file = Path(export_statespace)
            if not statespace_file.is_absolute():
                statespace_file = exe.parent / statespace_file
            statespace_file = safe_path(str(statespace_file))
            cmd.extend(["-x", str(statespace_file)])

        cmd.extend(list(args or []))
        proc = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout_seconds,
            cwd=str(exe.parent),
        )
        return {
            "executed": True,
            "exit_code": proc.returncode,
            "outcome": _classify_model_outcome(proc.returncode),
            "error": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "executed": False,
            "exit_code": None,
            "outcome": "timeout",
            "error": f"model.out timed out after {timeout_seconds}s",
        }
    except Exception as exc:
        return {
            "executed": False,
            "exit_code": None,
            "outcome": "unknown",
            "error": str(exc),
        }


def run_rmc_detailed(
    jar: str,
    model: str,
    property_file: str,
    output_dir: str,
    timeout_seconds: int = 120,
    jvm_opts: Optional[List[str]] = None,
    run_model_outcome: bool = False,
    model_out_timeout_seconds: int = 30,
    model_out_args: Optional[List[str]] = None,
    model_out_export_result: Optional[str] = None,
    model_out_hashmap_size: Optional[int] = None,
    model_out_export_statespace: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute RMC and return detailed phase and optional model.out outcomes."""
    jar_path = safe_path(jar)
    model_path = safe_path(model)
    property_path = safe_path(property_file)
    output_path = safe_path(output_dir)

    details: Dict[str, Any] = {
        "rmc_exit_code": 1,
        "rmc_outcome": "invalid_inputs",
        "cpp_generated": False,
        "cpp_compile_ok": False,
        "model_out": {
            "executed": False,
            "exit_code": None,
            "outcome": "not_run",
            "error": None,
        },
        "verification_outcome": "unknown",
        "result_artifact": {
            "path": None,
            "exists": False,
            "parsed": False,
            "format": "unknown",
            "outcome": "unknown",
            "error": None,
        },
        "output_dir": str(output_path),
        "executable_path": None,
    }

    # Validate inputs
    if not jar_path.exists():
        print(f"Error: JAR not found: {jar}", file=sys.stderr)
        return details
    if not model_path.exists():
        print(f"Error: Model not found: {model}", file=sys.stderr)
        return details
    if not property_path.exists():
        print(f"Error: Property not found: {property_file}", file=sys.stderr)
        return details

    output_path.mkdir(parents=True, exist_ok=True)

    # Build Java command
    cmd = ["java"]
    if jvm_opts:
        cmd.extend(jvm_opts)
    cmd.extend([
        "-jar", str(jar_path),
        "-s", str(model_path),
        "-p", str(property_path),
        "-o", str(output_path),
        "-e", "TIMED_REBECA",
        "-x"
    ])

    print("Executing RMC...", file=sys.stderr)
    print(f"Command: {' '.join(cmd)}", file=sys.stderr)

    # Execute with timeout
    stdout_log = output_path / "rmc_stdout.log"
    stderr_log = output_path / "rmc_stderr.log"
    compile_stderr_log = output_path / "compile_stderr.log"
    executable = output_path / "model.out"

    # Assert all output files are confined within the validated output_path
    for p in (stdout_log, stderr_log, compile_stderr_log, executable):
        if not str(p.resolve()).startswith(str(output_path)):
            print(f"Error: output file '{p}' escapes output directory", file=sys.stderr)
            details["rmc_outcome"] = "invalid_outputs"
            return details

    try:
        with open(stdout_log, 'w') as stdout_f, open(stderr_log, 'w') as stderr_f:
            result = subprocess.run(
                cmd,
                stdout=stdout_f,
                stderr=stderr_f,
                timeout=timeout_seconds,
                cwd=str(output_path)
            )
            if result.returncode != 0:
                print(f"RMC execution failed with exit code {result.returncode}", file=sys.stderr)
                details["rmc_exit_code"] = result.returncode
                details["rmc_outcome"] = "cex_or_rmc_failed"
                details["verification_outcome"] = "cex"
                return details
    except subprocess.TimeoutExpired:
        print(f"Error: RMC verification timed out after {timeout_seconds}s", file=sys.stderr)
        details["rmc_exit_code"] = 3
        details["rmc_outcome"] = "timeout"
        details["verification_outcome"] = "timeout"
        return details
    except Exception as e:
        print(f"Error executing RMC: {e}", file=sys.stderr)
        details["rmc_outcome"] = "rmc_exception"
        return details

    # Phase 1: Check if RMC generated C++ files (parse succeeded)
    cpp_files = [
        f for f in output_path.glob("*.cpp")
        if str(f.resolve()).startswith(str(output_path))
    ]
    if not cpp_files:
        print("Error: RMC failed to generate C++ files (parse error)", file=sys.stderr)
        print(f"Check {stderr_log} for Rebeca syntax errors", file=sys.stderr)
        details["rmc_exit_code"] = 5
        details["rmc_outcome"] = "parse_failed"
        details["verification_outcome"] = "unknown"
        return details

    print("✓ Phase 1: RMC generated C++ source files", file=sys.stderr)
    details["cpp_generated"] = True

    # Phase 2: Compile the C++ files with g++
    print("Phase 2: Compiling C++ files with g++...", file=sys.stderr)

    try:
        with open(compile_stderr_log, 'w') as stderr_f:
            result = subprocess.run(
                ["g++"] + [str(f) for f in cpp_files] + ["-w", "-o", str(executable)],
                stderr=stderr_f,
                cwd=str(output_path)
            )
            if result.returncode != 0:
                print("Error: Phase 2 failed - C++ compilation error", file=sys.stderr)
                print(f"Check {compile_stderr_log} for compiler errors", file=sys.stderr)
                print("Ensure g++ is installed: g++ --version", file=sys.stderr)
                details["rmc_exit_code"] = 4
                details["rmc_outcome"] = "cpp_compile_failed"
                details["verification_outcome"] = "unknown"
                return details
    except FileNotFoundError:
        print("Error: g++ compiler not found", file=sys.stderr)
        print("Install g++: Ubuntu/Debian: sudo apt install build-essential", file=sys.stderr)
        print("            macOS: xcode-select --install", file=sys.stderr)
        details["rmc_exit_code"] = 4
        details["rmc_outcome"] = "cpp_compile_failed"
        details["verification_outcome"] = "unknown"
        return details
    except Exception as e:
        print(f"Error during compilation: {e}", file=sys.stderr)
        details["rmc_exit_code"] = 4
        details["rmc_outcome"] = "cpp_compile_failed"
        details["verification_outcome"] = "unknown"
        return details

    if not executable.exists():
        print("Error: Compilation reported success but no executable found", file=sys.stderr)
        details["rmc_exit_code"] = 4
        details["rmc_outcome"] = "cpp_compile_failed"
        details["verification_outcome"] = "unknown"
        return details

    print("✓ Phase 2: C++ compilation succeeded", file=sys.stderr)
    details["cpp_compile_ok"] = True
    details["rmc_exit_code"] = 0
    details["rmc_outcome"] = "verified"
    details["executable_path"] = str(executable)

    if run_model_outcome:
        model_out_result = run_model_out(
            executable,
            timeout_seconds=model_out_timeout_seconds,
            args=model_out_args,
            export_result=model_out_export_result,
            hashmap_size=model_out_hashmap_size,
            export_statespace=model_out_export_statespace,
        )
        details["model_out"] = model_out_result

        parsed_result: Dict[str, Any] = {
            "path": None,
            "exists": False,
            "parsed": False,
            "format": "unknown",
            "outcome": "unknown",
            "error": None,
        }
        if model_out_export_result:
            try:
                result_file = Path(model_out_export_result)
                if not result_file.is_absolute():
                    result_file = executable.parent / result_file
                parsed_result = parse_rmc_result_file(str(result_file))
            except Exception as exc:
                parsed_result["error"] = str(exc)
        details["result_artifact"] = parsed_result

        model_outcome = model_out_result.get("outcome")
        artifact_outcome = parsed_result.get("outcome")
        if artifact_outcome in ("satisfied", "cex"):
            details["verification_outcome"] = artifact_outcome
        elif model_outcome in ("satisfied", "cex"):
            details["verification_outcome"] = model_outcome
        else:
            details["verification_outcome"] = "unknown"
    else:
        details["verification_outcome"] = "unknown"

    print("✓ RMC workflow complete (parse + compile)", file=sys.stderr)
    if run_model_outcome and details["model_out"]["executed"]:
        print(
            f"✓ model.out outcome: {details['model_out']['outcome']} "
            f"(exit={details['model_out']['exit_code']})",
            file=sys.stderr,
        )
    print(f"Output directory: {output_path}", file=sys.stderr)
    print(f"Executable: {executable}", file=sys.stderr)
    return details


def run_rmc(
    jar: str,
    model: str,
    property_file: str,
    output_dir: str,
    timeout_seconds: int = 120,
    jvm_opts: Optional[List[str]] = None
) -> int:
    """
    Execute RMC model checker.

    Returns:
        0: Success (parse + compile)
        1: Invalid inputs
        3: Timeout
        4: C++ compilation failed
        5: Rebeca parse failed
    """
    details = run_rmc_detailed(
        jar=jar,
        model=model,
        property_file=property_file,
        output_dir=output_dir,
        timeout_seconds=timeout_seconds,
        jvm_opts=jvm_opts,
        run_model_outcome=False,
    )
    return int(details["rmc_exit_code"])


def main():
    parser = argparse.ArgumentParser(description="Execute RMC model checker")
    parser.add_argument("--jar", required=True, help="Path to rmc.jar")
    parser.add_argument("--model", required=True, help="Path to .rebeca model file")
    parser.add_argument("--property", required=True, help="Path to .property file")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--timeout-seconds", type=int, default=120, help="Timeout in seconds")
    parser.add_argument("--jvm-opt", action="append", dest="jvm_opts", help="JVM options")
    parser.add_argument(
        "--run-model-outcome",
        action="store_true",
        help="Also execute compiled model.out and print semantic outcome",
    )
    parser.add_argument(
        "--output-json",
        action="store_true",
        help="Output the full RMC details payload as JSON to stdout",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        metavar="PATH",
        help=(
            "Write the full RMC details payload as JSON to PATH atomically (temp + rename). "
            "Preferred over parsing logs."
        ),
    )
    parser.add_argument(
        "--model-out-timeout-seconds",
        type=int,
        default=30,
        help="Timeout for model.out execution in seconds (default: 30)",
    )
    parser.add_argument(
        "--model-out-arg",
        action="append",
        dest="model_out_args",
        default=None,
        help="Argument to pass to model.out (repeatable)",
    )
    parser.add_argument(
        "--model-out-export-result",
        default=None,
        help="model.out: -o/--exportResult output file path",
    )
    parser.add_argument(
        "--model-out-hashmap-size",
        type=int,
        default=None,
        help="model.out: -s/--hashmapSize value (must be > 20)",
    )
    parser.add_argument(
        "--model-out-export-statespace",
        default=None,
        help="model.out: -x/--exportStatespace output file path",
    )

    args = parser.parse_args()

    needs_details_payload = bool(args.run_model_outcome or args.output_json or args.output_file)
    if needs_details_payload:
        details = run_rmc_detailed(
            jar=args.jar,
            model=args.model,
            property_file=args.property,
            output_dir=args.output_dir,
            timeout_seconds=args.timeout_seconds,
            jvm_opts=args.jvm_opts,
            run_model_outcome=bool(args.run_model_outcome),
            model_out_timeout_seconds=args.model_out_timeout_seconds,
            model_out_args=args.model_out_args,
            model_out_export_result=args.model_out_export_result,
            model_out_hashmap_size=args.model_out_hashmap_size,
            model_out_export_statespace=args.model_out_export_statespace,
        )

        if args.output_file:
            output_path = safe_path(args.output_file)
            _write_json_artifact(output_path, details)

        if args.output_json:
            print(json.dumps(details, indent=2, ensure_ascii=False))

        sys.exit(int(details["rmc_exit_code"]))

    sys.exit(
        run_rmc(
            args.jar,
            args.model,
            args.property,
            args.output_dir,
            args.timeout_seconds,
            args.jvm_opts,
        )
    )


if __name__ == "__main__":
    main()
