#!/usr/bin/env python3
"""Generate comprehensive per-rule report (JSON + Markdown)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from reporting_metrics import RuleReportBundle, build_rule_report_bundle
from utils import safe_path


def _slug_rule_name(value: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in value.strip())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "unknown-rule"


def _default_output_dir(rule_dir: Path, bundle: RuleReportBundle) -> Path:
    # Prefer the nearest ancestor named "output" for deterministic report placement.
    # Example: output/packaged/Rule-22 -> output/reports/Rule-22
    output_root = None
    for candidate in (rule_dir, *rule_dir.parents):
        if candidate.name == "output":
            output_root = candidate
            break

    if output_root is None:
        parent = rule_dir.parent
        base = parent if parent.name == "reports" else parent / "reports"
    else:
        base = output_root / "reports"

    return base / _slug_rule_name(bundle.rule_id)


def _bundle_to_json_payload(bundle: RuleReportBundle) -> Dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rule_id": bundle.rule_id,
        "status": bundle.status,
        "score_total": bundle.score_total,
        "score_breakdown": bundle.score_breakdown,
        "rubric_10pt": bundle.rubric_10pt,
        "failure_reasons": bundle.failure_reasons,
        "remediation_hints": bundle.remediation_hints,
        "metrics": {
            "mutation": bundle.mutation,
            "vacuity": bundle.vacuity,
            "model_property": bundle.model_property_stats,
            "mapping_delta": bundle.mapping_delta,
        },
        "artifacts": bundle.artifacts,
    }


def _bundle_to_markdown(payload: Dict[str, Any]) -> str:
    m = payload["metrics"]
    mutation = m["mutation"]
    vacuity = m["vacuity"]
    model_stats = m["model_property"]
    mapping_delta = m["mapping_delta"]

    lines = [
        f"# Rule Report — {payload['rule_id']}",
        "",
        "## Summary",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Status | {payload['status']} |",
        f"| Score | {payload['score_total']:.2f}/100 |",
        f"| Generated at (UTC) | {payload['generated_at']} |",
        "",
        "## Score Breakdown",
        "| Component | Value |",
        "|-----------|-------|",
    ]

    for key, value in payload["score_breakdown"].items():
        lines.append(f"| {key} | {value:.2f} |")

    if payload.get("rubric_10pt"):
        lines += [
            "",
            "## TQC 10-Point Rubric",
            "| Criterion | Score | Max | Method |",
            "|-----------|-------|-----|--------|",
        ]
        rubric = payload["rubric_10pt"]
        criterion_keys = [
            "syntax_correctness",
            "attribute_coverage",
            "actor_coverage",
            "hallucination_free",
            "logic_correctness",
        ]
        for key in criterion_keys:
            if key in rubric:
                c = rubric[key]
                score = c.get("score", 0)
                max_score = c.get("max", 1)
                method = c.get("method", "")
                lines.append(f"| {key} | {score} | {max_score} | {method} |")
        if "total" in rubric:
            total = rubric["total"]
            max_total = rubric.get("max", 10)
            lines.append(f"| **Total** | **{total}** | **{max_total}** | |")

    lines += [
        "",
        "## How to Interpret This Report",
        "- **Status** reflects the scoring decision for this rule (Pass/Fail/Conditional/Blocked/Unknown).",
        "- **Score** is on a 0–100 rubric and should be read together with the breakdown below.",
        "- **Mutation metrics** indicate semantic strength: higher killed/score generally means stronger properties.",
        "- **Vacuity diagnostics** indicate whether the property can pass for trivial reasons (e.g., unreachable precondition).",
        "- **Structure stats** help calibrate complexity and review effort (state variables, predicates, assertions).",
        "",
        "## Mutation Testing",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Mutants generated | {mutation['mutants_generated_total']} |",
        f"| Mutants selected | {mutation['mutants_selected_total'] if mutation['mutants_selected_total'] is not None else 'N/A'} |",
        f"| Mutants executed | {mutation['mutants_executed_total']} |",
        f"| Mutants killed | {mutation['mutants_killed_total']} |",
        f"| Mutants survived | {mutation['mutants_survived_total']} |",
        f"| Mutants errors | {mutation['mutants_error_total']} |",
        f"| Mutation score | {mutation['mutation_score'] if mutation['mutation_score'] is not None else 'N/A'} |",
        "",
        "### Mutation Interpretation",
        "- **Mutants generated**: total available mutation opportunities discovered.",
        "- **Mutants selected**: population selected for execution (sampling/budget may reduce this).",
        "- **Mutants executed**: actually run against RMC within budget/time limits.",
        "- **Killed/Survived**: killed means mutant changed semantic outcome; survived means no semantic flip.",
        "- **Mutation score**: $100 \\times \\frac{\\text{killed}}{\\text{executed}}$ when executed > 0.",
        "",
        "## Vacuity Diagnostics",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Checks total | {vacuity['checks_total']} |",
        f"| Checks vacuous | {vacuity['checks_vacuous']} |",
        f"| Checks non-vacuous | {vacuity['checks_non_vacuous']} |",
        f"| Checks unknown | {vacuity['checks_unknown']} |",
        f"| Overall | {vacuity['overall']} |",
        "",
        "### Vacuity Interpretation",
        "- **vacuous**: assertion passed but not for the intended semantic reason (usually weak/unreachable trigger).",
        "- **non_vacuous**: assertion meaningfully exercised.",
        "- **unknown**: vacuity evidence missing or inconclusive.",
        "",
    ]

    if vacuity["checks"]:
        lines += ["### Vacuity Checks"]
        for idx, check in enumerate(vacuity["checks"], 1):
            lines += [
                f"- Check {idx}",
                f"  - Assertion: {check.get('assertion_id')}",
                f"  - is_vacuous: {check.get('is_vacuous')}",
                f"  - basis: {check.get('comparison_basis')}",
                f"  - outcomes: {check.get('baseline_outcome')} -> {check.get('secondary_outcome')}",
                f"  - explanation: {check.get('explanation')}",
            ]
        lines += [""]

    lines += [
        "## Model/Property Structure Stats",
        "| Metric | Value |",
        "|--------|-------|",
        f"| State vars count | {model_stats['statevars_count']} |",
        f"| Predicates (define aliases) count | {model_stats['predicates_count']} |",
        f"| Assertions count | {model_stats['assertions_count']} |",
        "",
        "## Mapping Delta (if available)",
        "| Metric | Value |",
        "|--------|-------|",
    ]

    for key in (
        "statevars_added",
        "statevars_refined",
        "predicates_added",
        "predicates_refined",
        "assertions_added",
        "assertions_refined",
    ):
        val = mapping_delta.get(key)
        lines.append(f"| {key} | {val if val is not None else 'N/A'} |")

    if payload["failure_reasons"]:
        lines += ["", "## Failure Reasons"]
        lines.extend([f"- {x}" for x in payload["failure_reasons"]])

    if payload["remediation_hints"]:
        lines += ["", "## Remediation Hints"]
        lines.extend([f"- {x}" for x in payload["remediation_hints"]])

    lines += ["", "## Artifact Paths"]
    for k, v in payload["artifacts"].items():
        if v:
            lines.append(f"- {k}: `{v}`")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate comprehensive per-rule report")
    parser.add_argument("--rule-dir", required=True, help="Rule output directory (e.g., output/rule22)")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: sibling reports/<rule-id>/)",
    )
    parser.add_argument("--json-name", default="comprehensive_report.json", help="Output JSON filename")
    parser.add_argument("--md-name", default="comprehensive_report.md", help="Output markdown filename")
    parser.add_argument("--output-json", action="store_true", help="Also print JSON to stdout")
    args = parser.parse_args()

    rule_dir = safe_path(args.rule_dir)
    if not rule_dir.exists() or not rule_dir.is_dir():
        print(f"Error: rule output directory not found: {rule_dir}", file=sys.stderr)
        sys.exit(1)

    bundle = build_rule_report_bundle(rule_dir)
    if bundle is None:
        print(
            "Error: could not build rule report; expected at least one scorecard JSON under rule dir",
            file=sys.stderr,
        )
        sys.exit(1)

    payload = _bundle_to_json_payload(bundle)
    markdown = _bundle_to_markdown(payload)

    output_dir = safe_path(args.output_dir) if args.output_dir else _default_output_dir(rule_dir, bundle)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / args.json_name
    md_path = output_dir / args.md_name

    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")

    if args.output_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Comprehensive rule report written:\n- {json_path}\n- {md_path}")


if __name__ == "__main__":
    main()
