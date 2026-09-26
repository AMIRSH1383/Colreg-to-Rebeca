#!/usr/bin/env python3
"""
Vacuity Checker for Rebeca property verification.

Performs a secondary RMC pass that asserts !Precondition to confirm a property
is not passing trivially due to an impossible precondition.

Algorithm:
  1. Extract the first assertion expression from the Assertion block.
  2. Generate a negated-precondition property: Assertion { VacuityCheck: !Precondition; }
  3. Run RMC on the original model with the negated property.
  4. exit_code == 0  → !Precondition verified → original property was VACUOUS.
  5. exit_code != 0  → counterexample found  → original property is NON-VACUOUS (good).

Exit codes:
  0: Non-vacuous — property is meaningful
  1: Invalid inputs or runtime error
  2: Vacuous — property passes trivially (precondition is never reachable)
  3: Secondary RMC timeout
  4: Secondary RMC C++ compilation failure
  5: Secondary RMC parse failure
"""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from output_policy import vacuity_work_dirs
from run_rmc import run_rmc_detailed
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


def extract_precondition(
    property_content: str,
    assertion_id: Optional[str] = None,
) -> Optional[str]:
    """
    Extract an assertion expression from the Assertion block.

    Args:
        property_content: Full text of the .property file.
        assertion_id: If given, select the assertion whose label matches this
                      identifier (e.g. ``"Rule22"``).  If ``None`` (default)
                      the first assertion in the block is used.

    Example:
      Assertion { Rule22: !hasLight || (lightRange >= 6); }
      → "!hasLight || (lightRange >= 6)"

    Returns the expression string, or None if the block cannot be parsed.
    """
    if assertion_id is not None:
        # Targeted match: label must equal assertion_id exactly
        pattern = (
            r'\bAssertion\s*\{[^}]*?\b'
            + re.escape(assertion_id)
            + r'\s*:\s*(!?)(.+?);'
        )
        m = re.search(pattern, property_content, re.DOTALL)
    else:
        # Default: first assertion in the block
        m = re.search(
            r'\bAssertion\s*\{[^}]*?\w+\s*:\s*(!?)(.+?);',
            property_content,
            re.DOTALL,
        )
    if m is None:
        return None
    return (m.group(1) + m.group(2)).strip()


def build_negated_property(property_content: str, precondition: str) -> str:
    """
    Replace the Assertion block body with a single assertion of !Precondition.

    Simplifies double-negation: if precondition already starts with '!', the
    negated form becomes the positive expression. Preserves the define block
    and LTL block unchanged.
    """
    if precondition.startswith('!'):
        # Remove leading '!' and optional surrounding parens
        inner = precondition[1:].strip()
        negated = inner[1:-1] if (inner.startswith('(') and inner.endswith(')')) else inner
    else:
        negated = f"!({precondition})"

    negated_assertion = f"\n    VacuityCheck: {negated};\n  "
    return re.sub(
        r'(\bAssertion\s*\{)[^}]*(\})',
        lambda m: m.group(1) + negated_assertion + m.group(2),
        property_content,
        count=1,
        flags=re.DOTALL,
    )


def check_vacuity(
    jar: str,
    model: str,
    property_file: str,
    output_dir: str,
    timeout_seconds: int = 120,
    assertion_id: Optional[str] = None,
    rule_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Perform a vacuity check on a verified Rebeca property.

    Wraps run_rmc() — does not modify existing verification artifacts.
    Secondary and baseline RMC output is written to canonical subdirectories
    under the work tree (via :func:`output_policy.vacuity_work_dirs`) rather
    than sibling ``_vacuity``/``_baseline`` suffix directories.

    Args:
        jar:             Path to rmc.jar.
        model:           Path to .rebeca model file.
        property_file:   Path to .property file.
        output_dir:      Base output directory for this vacuity run.
        timeout_seconds: Per-run RMC timeout.
        assertion_id:    Label of the assertion to analyse.  Required when
                         multiple assertions exist.
        rule_id:         Optional rule identifier used to place scratch dirs
                         under the canonical work tree.  When omitted, dirs are
                         placed as ``<output_dir>/vacuity/`` and
                         ``<output_dir>/baseline/``.

    Returns:
        {
          "is_vacuous":            bool | None,
          "precondition_used":     str | None,
          "assertion_id_used":     str | None,
          "baseline_outcome":      str | None,
          "secondary_outcome":     str | None,
          "comparison_changed":    bool | None,
          "comparison_basis":      str,
          "secondary_exit_code":   int,
          "secondary_output_dir":  str | None,
          "explanation":           str
        }
    """
    prop_path = safe_path(property_file)
    if not prop_path.exists():
        return {
            "is_vacuous": None,
            "precondition_used": None,
            "baseline_outcome": None,
            "secondary_outcome": None,
            "comparison_changed": None,
            "comparison_basis": "none",
            "secondary_exit_code": 1,
            "secondary_output_dir": None,
            "explanation": f"Property file not found: {property_file}",
        }

    property_content = prop_path.read_text(encoding="utf-8")

    # Warn when multiple assertions exist and no assertion_id was specified —
    # silently defaulting to the first assertion is a common source of vacuity
    # result mismatches between this tool and score_rule.py.
    if assertion_id is None:
        # Extract the full Assertion block, then collect all label: entries inside it.
        _block = re.search(r'\bAssertion\s*\{([^}]*)\}', property_content, re.DOTALL)
        all_labels = re.findall(r'(\w+)\s*:', _block.group(1)) if _block else []
        if len(all_labels) > 1:
            print(
                f"[vacuity_checker] WARNING: {len(all_labels)} assertions found "
                f"({', '.join(all_labels[:5])}{'...' if len(all_labels) > 5 else ''}). "
                "Defaulting to the first assertion. "
                "Pass --assertion-id to select a specific one and avoid ambiguity.",
                file=sys.stderr,
            )
            labels = ", ".join(all_labels)
            return {
                "is_vacuous": None,
                "precondition_used": None,
                "assertion_id_used": None,
                "baseline_outcome": None,
                "secondary_outcome": None,
                "comparison_changed": None,
                "comparison_basis": "none",
                "secondary_exit_code": 1,
                "secondary_output_dir": None,
                "explanation": (
                    f"Ambiguous: {len(all_labels)} assertions found ({labels}). "
                    "Pass --assertion-id to select one. "
                    f"Available: {labels}"
                ),
            }

    precondition = extract_precondition(property_content, assertion_id=assertion_id)

    if precondition is None:
        detail = (
            f" (assertion_id={assertion_id!r})" if assertion_id else " (first assertion)"
        )
        return {
            "is_vacuous": None,
            "precondition_used": None,
            "assertion_id_used": assertion_id,
            "baseline_outcome": None,
            "secondary_outcome": None,
            "comparison_changed": None,
            "comparison_basis": "none",
            "secondary_exit_code": 1,
            "secondary_output_dir": None,
            "explanation": f"Could not extract precondition from Assertion block{detail}",
        }

    negated_content = build_negated_property(property_content, precondition)

    # Use canonical policy paths — never string-suffix sibling directories.
    secondary_output, baseline_output = vacuity_work_dirs(
        output_dir, rule_id=rule_id
    )
    baseline_details = run_rmc_detailed(
        jar=jar,
        model=model,
        property_file=property_file,
        output_dir=baseline_output,
        timeout_seconds=timeout_seconds,
        run_model_outcome=True,
        model_out_timeout_seconds=timeout_seconds,
    )
    baseline_outcome = baseline_details.get("verification_outcome")

    # Write the negated property to a temp file inside ~ so safe_path() allows it.
    # Always clean up afterwards.
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".property", delete=False, encoding="utf-8",
            dir=Path.home(),
        ) as tmp:
            tmp.write(negated_content)
            tmp_path = Path(tmp.name)

        secondary_details = run_rmc_detailed(
            jar=jar,
            model=model,
            property_file=str(tmp_path),
            output_dir=secondary_output,
            timeout_seconds=timeout_seconds,
            run_model_outcome=True,
            model_out_timeout_seconds=timeout_seconds,
        )
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    exit_code = int(secondary_details.get("rmc_exit_code", 1))
    secondary_outcome = secondary_details.get("verification_outcome")

    comparable = baseline_outcome in ("satisfied", "cex") and secondary_outcome in ("satisfied", "cex")
    if comparable:
        comparison_changed = baseline_outcome != secondary_outcome
        # Vacuous means negated-precondition check preserves the same verdict.
        is_vacuous = not comparison_changed
        comparison_basis = "semantic_outcome"
    else:
        # Legacy fallback: preserve historical behavior when semantic outcome
        # cannot be derived (timeouts/errors/non-comparable states).
        comparison_changed = None
        is_vacuous = exit_code == 0
        comparison_basis = "legacy_secondary_exit"

    if comparable:
        explanation = (
            "VACUOUS: baseline and negated-precondition runs produced the same semantic outcome "
            f"({baseline_outcome})."
            if is_vacuous
            else "NON-VACUOUS: baseline and negated-precondition outcomes differ "
                 f"({baseline_outcome} -> {secondary_outcome})."
        )
    else:
        explanation = (
            "VACUOUS: The property passes trivially — its precondition is never reachable."
            if is_vacuous
            else "NON-VACUOUS: A counterexample exists for !Precondition; the property is meaningful."
        )

    return {
        "is_vacuous": is_vacuous,
        "precondition_used": precondition,
        "assertion_id_used": assertion_id,
        "baseline_outcome": baseline_outcome,
        "secondary_outcome": secondary_outcome,
        "comparison_changed": comparison_changed,
        "comparison_basis": comparison_basis,
        "secondary_exit_code": exit_code,
        "secondary_output_dir": secondary_output,
        "explanation": explanation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Vacuity check: verify a Rebeca property is not passing trivially"
    )
    parser.add_argument("--jar", required=True, help="Path to rmc.jar")
    parser.add_argument("--model", required=True, help="Path to .rebeca model file")
    parser.add_argument("--property", required=True, help="Path to .property file")
    parser.add_argument(
        "--output-dir",
        required=True,
        help=(
            "Base output directory used for vacuity scratch work. When --rule-id is provided, "
            "canonical subdirectories are created under output/work/<rule-id>/runs/{baseline,vacuity}/. "
            "When omitted, scratch dirs are created inside --output-dir."
        ),
    )
    parser.add_argument(
        "--timeout-seconds", type=int, default=120, help="RMC timeout in seconds"
    )
    parser.add_argument(
        "--assertion-id",
        default=None,
        help="Label of the assertion to analyse (e.g. 'Rule22'). "
             "Defaults to the first assertion in the Assertion block. "
             "Required when multiple assertions exist to avoid ambiguity.",
    )
    parser.add_argument(
        "--rule-id",
        default=None,
        help="Rule identifier used to place vacuity scratch dirs under the "
             "canonical work tree (output/work/<rule-id>/runs/vacuity/). "
             "When omitted, dirs are placed inside --output-dir.",
    )
    parser.add_argument("--output-json", action="store_true", help="Output result as JSON")
    parser.add_argument(
        "--output-file",
        default=None,
        metavar="PATH",
        help="Write the result payload as JSON to PATH atomically (temp + rename)",
    )
    args = parser.parse_args()

    result = check_vacuity(
        jar=args.jar,
        model=args.model,
        property_file=args.property,
        output_dir=args.output_dir,
        timeout_seconds=args.timeout_seconds,
        assertion_id=args.assertion_id,
        rule_id=args.rule_id,
    )

    if args.output_file:
        output_path = safe_path(args.output_file)
        _write_json_artifact(output_path, result)

    is_ambiguous = (
        result["is_vacuous"] is None
        and "Ambiguous" in str(result.get("explanation", ""))
    )

    if is_ambiguous:
        if args.output_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Precondition:            {result['precondition_used']}")
            print(f"Is Vacuous:              {result['is_vacuous']}")
            print(f"Secondary RMC exit code: {result['secondary_exit_code']}")
            print(f"Explanation:             {result['explanation']}")
            if result["secondary_output_dir"]:
                print(f"Secondary output dir:    {result['secondary_output_dir']}")
        print(
            "ERROR: Ambiguous assertion selection. Pass --assertion-id with one of the available labels.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Precondition:            {result['precondition_used']}")
        print(f"Is Vacuous:              {result['is_vacuous']}")
        print(f"Secondary RMC exit code: {result['secondary_exit_code']}")
        print(f"Explanation:             {result['explanation']}")
        if result["secondary_output_dir"]:
            print(f"Secondary output dir:    {result['secondary_output_dir']}")

    if result["is_vacuous"] is True:
        sys.exit(2)
    elif result["is_vacuous"] is False:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
