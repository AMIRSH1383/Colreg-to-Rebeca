#!/usr/bin/env python3
"""Consolidate multiple per-rule translation folders into one aggregate report."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Tuple

from reporting_metrics import RuleReportBundle, build_rule_report_bundle, summarize_status_counts
from utils import safe_path


def _load_plotting():
    try:
        import matplotlib.pyplot as plt  # type: ignore

        return plt
    except Exception:
        return None


def _configure_plot_style(plt: Any) -> None:
    # TeX-like typography without requiring external LaTeX runtime.
    plt.rcParams["font.family"] = "serif"
    plt.rcParams["font.serif"] = ["Computer Modern Roman", "CMU Serif", "DejaVu Serif"]
    plt.rcParams["mathtext.fontset"] = "cm"
    plt.rcParams["svg.fonttype"] = "none"


def _save_figure(fig: Any, base_path: Path) -> Dict[str, str]:
    svg_path = base_path.with_suffix(".svg")
    png_path = base_path.with_suffix(".png")
    fig.savefig(svg_path, format="svg", bbox_inches="tight")
    fig.savefig(png_path, format="png", dpi=300, bbox_inches="tight")
    return {"svg": str(svg_path), "png": str(png_path)}


def _plot_status_counts(plt: Any, counts: Dict[str, int], out_dir: Path) -> Dict[str, str]:
    labels = list(counts.keys())
    values = [counts[k] for k in labels]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(labels, values)
    ax.set_title("Rule Status Distribution")
    ax.set_ylabel("Count")
    ax.set_xlabel("Status")
    for i, v in enumerate(values):
        ax.text(i, v, str(v), ha="center", va="bottom")
    fig.tight_layout()
    paths = _save_figure(fig, out_dir / "status_distribution")
    plt.close(fig)
    return paths


def _plot_rule_scores(plt: Any, bundles: List[RuleReportBundle], out_dir: Path) -> Dict[str, str]:
    labels = [b.rule_id for b in bundles]
    values = [b.score_total for b in bundles]
    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 1.2), 4.8))
    ax.bar(labels, values)
    ax.set_ylim(0, 100)
    ax.set_title("Score by Rule")
    ax.set_ylabel("Score")
    ax.set_xlabel("Rule")
    for i, v in enumerate(values):
        ax.text(i, v, f"{v:.1f}", ha="center", va="bottom")
    fig.tight_layout()
    paths = _save_figure(fig, out_dir / "scores_by_rule")
    plt.close(fig)
    return paths


def _plot_mutation_stacked(plt: Any, bundles: List[RuleReportBundle], out_dir: Path) -> Dict[str, str]:
    labels = [b.rule_id for b in bundles]
    killed = [int(b.mutation.get("mutants_killed_total", 0) or 0) for b in bundles]
    survived = [int(b.mutation.get("mutants_survived_total", 0) or 0) for b in bundles]
    errors = [int(b.mutation.get("mutants_error_total", 0) or 0) for b in bundles]

    fig, ax = plt.subplots(figsize=(max(8, len(labels) * 1.2), 5.0))
    ax.bar(labels, killed, label="Killed")
    ax.bar(labels, survived, bottom=killed, label="Survived")
    tops = [k + s for k, s in zip(killed, survived)]
    ax.bar(labels, errors, bottom=tops, label="Error")
    ax.set_title("Mutation Outcomes by Rule")
    ax.set_ylabel("Mutants")
    ax.set_xlabel("Rule")
    ax.legend()
    fig.tight_layout()
    paths = _save_figure(fig, out_dir / "mutation_outcomes")
    plt.close(fig)
    return paths


def _plot_cactus(plt: Any, bundles: List[RuleReportBundle], out_dir: Path) -> Dict[str, str]:
    # Cactus: x is solved instances count, y is sorted quality metric (score).
    sorted_scores = sorted([b.score_total for b in bundles])
    xs = list(range(1, len(sorted_scores) + 1))
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.step(xs, sorted_scores, where="post")
    ax.set_title("Cactus Plot (Rule Scores)")
    ax.set_xlabel("Number of Rules")
    ax.set_ylabel("Score")
    ax.set_ylim(0, 100)
    fig.tight_layout()
    paths = _save_figure(fig, out_dir / "cactus_scores")
    plt.close(fig)
    return paths


def _discover_rule_dirs(root_output_dir: Path) -> List[Path]:
    out: List[Path] = []
    for child in sorted(root_output_dir.iterdir()):
        if not child.is_dir():
            continue
        if list(child.glob("scorecard*.json")) or list(child.glob("*score*.json")):
            out.append(child)
    return out


def _aggregate_json(bundles: List[RuleReportBundle], plot_paths: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    status_counts = summarize_status_counts(bundles)
    total = len(bundles)
    scores = [b.score_total for b in bundles]

    mutation_generated_total = sum(int(b.mutation.get("mutants_generated_total", 0) or 0) for b in bundles)
    mutation_selected_total = sum(int(b.mutation.get("mutants_selected_total", 0) or 0) for b in bundles if b.mutation.get("mutants_selected_total") is not None)
    mutation_executed_total = sum(int(b.mutation.get("mutants_executed_total", 0) or 0) for b in bundles)
    mutation_killed_total = sum(int(b.mutation.get("mutants_killed_total", 0) or 0) for b in bundles)
    mutation_survived_total = sum(int(b.mutation.get("mutants_survived_total", 0) or 0) for b in bundles)
    mutation_error_total = sum(int(b.mutation.get("mutants_error_total", 0) or 0) for b in bundles)
    mutation_scores = [float(b.mutation["mutation_score"]) for b in bundles if b.mutation.get("mutation_score") is not None]

    statevars_count_total = sum(int(b.model_property_stats.get("statevars_count", 0) or 0) for b in bundles)
    predicates_count_total = sum(int(b.model_property_stats.get("predicates_count", 0) or 0) for b in bundles)
    assertions_count_total = sum(int(b.model_property_stats.get("assertions_count", 0) or 0) for b in bundles)

    def _sum_opt(field: str) -> int:
        return sum(int(b.mapping_delta[field] or 0) for b in bundles)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_rules": total,
            "rules_passed": status_counts.get("Pass", 0),
            "rules_failed": status_counts.get("Fail", 0),
            "rules_conditional": status_counts.get("Conditional", 0),
            "rules_blocked": status_counts.get("Blocked", 0),
            "rules_unknown": status_counts.get("Unknown", 0),
            "success_rate": round((status_counts.get("Pass", 0) / total), 4) if total else 0.0,
            "score_mean": round(mean(scores), 2) if scores else 0.0,
            "score_min": round(min(scores), 2) if scores else 0.0,
            "score_max": round(max(scores), 2) if scores else 0.0,
        },
        "status_counts": status_counts,
        "mutation_stats": {
            "mutants_generated_total": mutation_generated_total,
            "mutants_selected_total": mutation_selected_total,
            "mutants_executed_total": mutation_executed_total,
            "mutants_killed_total": mutation_killed_total,
            "mutants_survived_total": mutation_survived_total,
            "mutants_error_total": mutation_error_total,
            "mutation_score_mean": round(mean(mutation_scores), 2) if mutation_scores else None,
        },
        "model_property_stats": {
            "statevars_count_total": statevars_count_total,
            "predicates_count_total": predicates_count_total,
            "assertions_count_total": assertions_count_total,
        },
        "mapping_delta_totals": {
            "statevars_added_total": _sum_opt("statevars_added"),
            "statevars_refined_total": _sum_opt("statevars_refined"),
            "predicates_added_total": _sum_opt("predicates_added"),
            "predicates_refined_total": _sum_opt("predicates_refined"),
            "assertions_added_total": _sum_opt("assertions_added"),
            "assertions_refined_total": _sum_opt("assertions_refined"),
        },
        "plots": plot_paths,
        "per_rule": [asdict(b) for b in bundles],
    }


def _to_markdown(payload: Dict[str, Any]) -> str:
    s = payload["summary"]
    m = payload["mutation_stats"]
    mp = payload["model_property_stats"]
    delta = payload["mapping_delta_totals"]

    lines = [
        "# Consolidated Legata→Rebeca Report",
        "",
        "## Summary",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total rules | {s['total_rules']} |",
        f"| Rules passed | {s['rules_passed']} |",
        f"| Rules failed | {s['rules_failed']} |",
        f"| Rules conditional | {s['rules_conditional']} |",
        f"| Rules blocked | {s['rules_blocked']} |",
        f"| Rules unknown | {s['rules_unknown']} |",
        f"| Success rate | {s['success_rate']:.1%} |",
        f"| Score mean | {s['score_mean']} |",
        f"| Score min | {s['score_min']} |",
        f"| Score max | {s['score_max']} |",
        "",
        "## Mutation Aggregate Stats",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Mutants generated total | {m['mutants_generated_total']} |",
        f"| Mutants selected total | {m['mutants_selected_total']} |",
        f"| Mutants executed total | {m['mutants_executed_total']} |",
        f"| Mutants killed total | {m['mutants_killed_total']} |",
        f"| Mutants survived total | {m['mutants_survived_total']} |",
        f"| Mutants errors total | {m['mutants_error_total']} |",
        f"| Mutation score mean | {m['mutation_score_mean'] if m['mutation_score_mean'] is not None else 'N/A'} |",
        "",
        "## Model/Property Aggregate Stats",
        "| Metric | Value |",
        "|--------|-------|",
        f"| State vars total | {mp['statevars_count_total']} |",
        f"| Predicates total | {mp['predicates_count_total']} |",
        f"| Assertions total | {mp['assertions_count_total']} |",
        "",
        "## Mapping Delta Totals",
        "| Metric | Value |",
        "|--------|-------|",
    ]

    for k, v in delta.items():
        lines.append(f"| {k} | {v} |")

    lines += ["", "## Status Distribution"]
    for k, v in payload["status_counts"].items():
        lines.append(f"- **{k}**: {v}")

    if payload.get("plots"):
        lines += ["", "## Plots"]
        for name, files in payload["plots"].items():
            lines.append(f"- {name}: SVG `{files.get('svg')}`, PNG `{files.get('png')}`")

    lines += ["", "## Per-Rule Table", "", "| Rule | Status | Score | Mutants Gen | Mutants Run | Killed | Survived | Errors |", "|------|--------|-------|-------------|-------------|--------|----------|--------|"]
    for r in payload["per_rule"]:
        mm = r["mutation"]
        lines.append(
            "| {rule} | {status} | {score:.2f} | {gen} | {run} | {k} | {s} | {e} |".format(
                rule=r["rule_id"],
                status=r["status"],
                score=float(r["score_total"]),
                gen=int(mm.get("mutants_generated_total", 0) or 0),
                run=int(mm.get("mutants_executed_total", 0) or 0),
                k=int(mm.get("mutants_killed_total", 0) or 0),
                s=int(mm.get("mutants_survived_total", 0) or 0),
                e=int(mm.get("mutants_error_total", 0) or 0),
            )
        )

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Consolidate multiple rule folders into one report")
    parser.add_argument("--root-output-dir", required=True, help="Root output folder containing per-rule folders")
    parser.add_argument("--output-dir", required=True, help="Destination directory for consolidated report")
    parser.add_argument("--skip-plots", action="store_true", help="Skip graph generation")
    parser.add_argument("--output-json", action="store_true", help="Also print consolidated JSON")
    args = parser.parse_args()

    root_output_dir = safe_path(args.root_output_dir)
    if not root_output_dir.exists() or not root_output_dir.is_dir():
        print(f"Error: root output dir not found: {root_output_dir}", file=sys.stderr)
        sys.exit(1)

    output_dir = safe_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rule_dirs = _discover_rule_dirs(root_output_dir)
    if not rule_dirs:
        print("Error: no rule folders found (expected scorecard JSON under child dirs)", file=sys.stderr)
        sys.exit(1)

    bundles: List[RuleReportBundle] = []
    for rule_dir in rule_dirs:
        bundle = build_rule_report_bundle(rule_dir)
        if bundle:
            bundles.append(bundle)

    if not bundles:
        print("Error: discovered rule folders but failed to parse any report bundle", file=sys.stderr)
        sys.exit(1)

    plot_paths: Dict[str, Dict[str, str]] = {}
    if not args.skip_plots:
        plt = _load_plotting()
        if plt is None:
            print(
                "Error: matplotlib is required for plot generation. Install matplotlib or use --skip-plots.",
                file=sys.stderr,
            )
            sys.exit(1)
        _configure_plot_style(plt)
        plot_paths["status_distribution"] = _plot_status_counts(plt, summarize_status_counts(bundles), output_dir)
        plot_paths["scores_by_rule"] = _plot_rule_scores(plt, bundles, output_dir)
        plot_paths["mutation_outcomes"] = _plot_mutation_stacked(plt, bundles, output_dir)
        plot_paths["cactus_scores"] = _plot_cactus(plt, bundles, output_dir)

    payload = _aggregate_json(bundles, plot_paths)
    markdown = _to_markdown(payload)

    json_path = output_dir / "consolidated_report.json"
    md_path = output_dir / "consolidated_report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")

    if args.output_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Consolidated report written:\n- {json_path}\n- {md_path}")
        if plot_paths:
            print("Plots generated (SVG + PNG):")
            for name, files in plot_paths.items():
                print(f"- {name}: {files['svg']}, {files['png']}")


if __name__ == "__main__":
    main()
