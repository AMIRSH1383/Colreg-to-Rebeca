#!/usr/bin/env python3
"""
Aggregate scoring report generator.

Accepts per-rule scorecards as:
  • A JSON array  (``[{...}, {...}]``)
  • NDJSON stream (one compact JSON object per line)
  • A JSON object with a ``per_rule_scorecards`` list key

Scorecard status normalisation
-------------------------------
Recognised ``status`` values (case-insensitive):
  pass / passed       → "Pass"
  fail / failed       → "Fail"
  conditional         → "Conditional"
  blocked             → "Blocked"
  unknown             → "Unknown"
"""

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

from utils import safe_path

# ── status normalisation ────────────────────────────────────────────────────

_STATUS_MAP: Dict[str, str] = {
    "pass": "Pass",
    "passed": "Pass",
    "fail": "Fail",
    "failed": "Fail",
    "conditional": "Conditional",
    "blocked": "Blocked",
    "unknown": "Unknown",
}


def _normalise_status(raw: str) -> str:
    return _STATUS_MAP.get(str(raw).lower().strip(), "Unknown")


def _slug_rule_name(value: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in value.strip())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "unknown-rule"


# ── scorecard loader ─────────────────────────────────────────────────────────

def _load_scorecards(source: str) -> List[Dict[str, Any]]:
    """
    Resolve scorecards from:
      - a JSON array string / file path
      - an NDJSON stream (one object per line)
      - a JSON object with a ``per_rule_scorecards`` key
    """
    text = source.strip()

    # Try treating source as a file path only when it looks like a path
    # (not a JSON literal).  Guard against OSError on filenames that are
    # too long or contain illegal characters.
    if text and text[0] not in ("{", "[") and "\n" not in text:
        try:
            candidate = Path(text)
            if candidate.exists() and candidate.is_file():
                text = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            pass  # not a valid path — treat as raw JSON/NDJSON

    # JSON array — unambiguous
    if text.startswith("["):
        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError("Expected a JSON array at top level")
        return parsed

    # NDJSON: multiple non-blank lines each starting with '{'
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) > 1 and all(l.startswith("{") for l in lines):
        cards = []
        for lineno, line in enumerate(lines, 1):
            try:
                cards.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"NDJSON parse error on line {lineno}: {exc}") from exc
        return cards

    # Single JSON object (possibly with per_rule_scorecards key)
    if text.startswith("{"):
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "per_rule_scorecards" in parsed:
            return parsed["per_rule_scorecards"]
        return [parsed]

    # Last-chance NDJSON (lines may not all start with '{')
    if lines:
        cards = []
        for lineno, line in enumerate(lines, 1):
            try:
                cards.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"NDJSON parse error on line {lineno}: {exc}") from exc
        return cards

    raise ValueError("Input is empty or unrecognised format")


# ── ReportGenerator ──────────────────────────────────────────────────────────

class ReportGenerator:
    """Generates compact and detailed scoring reports."""

    def __init__(self) -> None:
        self.report_data: Dict[str, Any] = {
            "execution_timestamp": None,
            "total_rules": 0,
            "rules_passed": 0,
            "rules_failed": 0,
            "score_mean": 0.0,
            "score_min": 0,
            "score_max": 0,
            "success_rate": 0.0,
            "status_counts": {
                "Pass": 0,
                "Fail": 0,
                "Conditional": 0,
                "Blocked": 0,
                "Unknown": 0,
            },
            "score_breakdown": {
                "base_10pt":     0,
                "base_10pt_pct": 0.0,
                "vacuity_pct":  0.0,
                "mutation_pct": 0.0,
            },
            "fallback_usage_count": 0,
            "blocked_rules_count": 0,
            "per_rule_scorecards": [],
            "top_failure_reasons": [],
            "aggregate_remediation_hints": [],
        }

    def add_scorecard(self, scorecard: Dict[str, Any]) -> None:
        """Add a rule scorecard to the report."""
        # Normalise status before appending
        if "status" in scorecard:
            scorecard = dict(scorecard)  # immutable copy
            scorecard["status"] = _normalise_status(scorecard["status"])
        self.report_data["per_rule_scorecards"].append(scorecard)
        self.report_data["total_rules"] += 1

    def finalize(self) -> None:
        """Finalize aggregate metrics from the accumulated per_rule_scorecards."""
        cards = self.report_data["per_rule_scorecards"]
        if not cards:
            return

        scores: List[float] = []
        failure_reasons: List[str] = []
        remediation_hints: List[str] = []
        bd_sums: Dict[str, float] = {k: 0.0 for k in self.report_data["score_breakdown"]}
        status_counts: Dict[str, int] = {k: 0 for k in self.report_data["status_counts"]}

        for card in cards:
            status = _normalise_status(card.get("status", "Unknown"))
            status_counts[status] = status_counts.get(status, 0) + 1

            score = card.get("score_total", 0)
            try:
                scores.append(float(score))
            except (TypeError, ValueError):
                scores.append(0.0)

            bd = card.get("score_breakdown", {})
            for key in bd_sums:
                try:
                    bd_sums[key] += float(bd.get(key, 0))
                except (TypeError, ValueError):
                    pass

            if card.get("mapping_path") in ("colreg-fallback", "synthesis"):
                self.report_data["fallback_usage_count"] += 1

            for reason in card.get("failure_reasons", []):
                failure_reasons.append(reason)
            for hint in card.get("remediation_hints", []):
                remediation_hints.append(hint)

        # Aggregate counters
        n = len(cards)
        self.report_data["rules_passed"] = status_counts.get("Pass", 0)
        self.report_data["rules_failed"] = (
            status_counts.get("Fail", 0)
            + status_counts.get("Blocked", 0)
            + status_counts.get("Unknown", 0)
        )
        self.report_data["blocked_rules_count"] = status_counts.get("Blocked", 0)
        self.report_data["status_counts"] = {
            k: v for k, v in status_counts.items()
        }

        # Score statistics
        self.report_data["score_mean"] = round(mean(scores), 2) if scores else 0.0
        self.report_data["score_min"] = int(min(scores)) if scores else 0
        self.report_data["score_max"] = int(max(scores)) if scores else 0
        self.report_data["success_rate"] = (
            round(self.report_data["rules_passed"] / n, 4) if n > 0 else 0.0
        )

        # Breakdown averages
        self.report_data["score_breakdown"] = {
            k: round(v / n, 2) for k, v in bd_sums.items()
        }

        # Dedup failure reasons / hints, preserve order
        seen: set = set()
        deduped_reasons: List[str] = []
        for r in failure_reasons:
            if r not in seen:
                seen.add(r)
                deduped_reasons.append(r)
        self.report_data["top_failure_reasons"] = deduped_reasons[:10]

        seen = set()
        deduped_hints: List[str] = []
        for h in remediation_hints:
            if h not in seen:
                seen.add(h)
                deduped_hints.append(h)
        self.report_data["aggregate_remediation_hints"] = deduped_hints[:10]

    def to_json(self) -> str:
        """Export report as JSON."""
        return json.dumps(self.report_data, indent=2)

    def to_markdown(self) -> str:
        """Export report as Markdown."""
        d = self.report_data
        lines = [
            "# Legata→Rebeca Transformation Report",
            "",
            "## Summary",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total rules | {d['total_rules']} |",
            f"| Rules passed | {d['rules_passed']} |",
            f"| Rules failed | {d['rules_failed']} |",
            f"| Success rate | {d['success_rate']:.1%} |",
            f"| Score mean | {d['score_mean']} |",
            f"| Score min | {d['score_min']} |",
            f"| Score max | {d['score_max']} |",
            f"| Fallback usage | {d['fallback_usage_count']} |",
            f"| Blocked rules | {d['blocked_rules_count']} |",
            "",
            "## Status Distribution",
        ]
        for status, count in d.get("status_counts", {}).items():
            lines.append(f"- **{status}**: {count}")
        lines += [
            "",
            "## Score Breakdown (averages)",
        ]
        for component, score in d.get("score_breakdown", {}).items():
            lines.append(f"- **{component}**: {score}")
        if d.get("top_failure_reasons"):
            lines += ["", "## Top Failure Reasons"]
            for reason in d["top_failure_reasons"]:
                lines.append(f"- {reason}")
        if d.get("aggregate_remediation_hints"):
            lines += ["", "## Remediation Hints"]
            for hint in d["aggregate_remediation_hints"]:
                lines.append(f"- {hint}")
        lines += ["", "## Per-Rule Scorecards", ""]
        for card in d.get("per_rule_scorecards", []):
            rule_id = card.get("rule_id", "?")
            status = card.get("status", "?")
            score = card.get("score_total", 0)
            lines.append(f"### {rule_id} — {status} ({score}/100)")
            if card.get("failure_reasons"):
                for r in card["failure_reasons"]:
                    lines.append(f"  - {r}")
            lines.append("")
        return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def _resolve_report_output_dir(output_dir: Path, cards: List[Dict[str, Any]]) -> Path:
    """Resolve an output directory for summary.json/summary.md.

    Historical behavior: treat --output-dir as a *base* and always nest outputs
    under a trailing ``reports/`` directory.

    However, callers sometimes pass an already-resolved per-rule directory like
    ``output/reports/<rule_id>``. In that case we must NOT add an extra
    ``reports/<rule_id>`` layer (which causes duplicated trees).
    """

    if len(cards) == 1:
        rid = cards[0].get("rule_id")
        slug = _slug_rule_name(rid) if isinstance(rid, str) and rid.strip() else None

        # If the caller already provided a per-rule directory under .../reports/<rule_id>,
        # treat it as final.
        if slug and output_dir.name == slug and output_dir.parent.name == "reports":
            return output_dir
        if output_dir.name == "single-rule" and output_dir.parent.name == "reports":
            return output_dir
    else:
        # If the caller already provided .../reports/aggregate, treat it as final.
        if output_dir.name == "aggregate" and output_dir.parent.name == "reports":
            return output_dir

    base = output_dir if output_dir.name == "reports" else output_dir / "reports"
    if len(cards) == 1:
        rid = cards[0].get("rule_id")
        if isinstance(rid, str) and rid.strip():
            return base / _slug_rule_name(rid)
        return base / "single-rule"
    return base / "aggregate"


def _emit_stdout(gen: ReportGenerator, fmt: str) -> None:
    if fmt in ("json", "both"):
        print(gen.to_json())
    if fmt in ("markdown", "both"):
        print(gen.to_markdown())


def _write_verification_json(gen: ReportGenerator, output_dir: Path) -> None:
    """Write verification.json with per-rule verification outcomes (canonical Step08 output)."""
    cards = gen.report_data["per_rule_scorecards"]
    records = []
    for card in cards:
        vacuity = card.get("vacuity") or {}
        records.append({
            "rule_id": card.get("rule_id"),
            "status": card.get("status"),
            "score_total": card.get("score_total"),
            "verified": card.get("status") in ("Pass", "Conditional"),
            "vacuity_status": vacuity.get("status", "unchecked"),
            "is_vacuous": vacuity.get("is_vacuous"),
        })
    (output_dir / "verification.json").write_text(
        json.dumps({"rules": records, "total": len(records)}, indent=2),
        encoding="utf-8",
    )


def _write_quality_gates_json(gen: ReportGenerator, output_dir: Path) -> None:
    """Write quality_gates.json with gate pass/fail per rule (canonical Step08 output)."""
    d = gen.report_data
    per_rule: Dict[str, Any] = {}
    for card in d["per_rule_scorecards"]:
        rule_id = card.get("rule_id", "unknown")
        score = card.get("score_total", 0)
        status = card.get("status", "Unknown")
        is_vacuous = (card.get("vacuity") or {}).get("is_vacuous", None)
        bd = card.get("score_breakdown", {})
        per_rule[rule_id] = {
            "score_above_threshold": score >= 80,
            "syntax_ok": (bd.get("syntax") or 0) >= 10,
            "verified": status in ("Pass", "Conditional"),
            "non_vacuous": is_vacuous is not True,
            "mutation_ok": (bd.get("semantic_alignment") or 0) >= 44,
            "gate_passed": score >= 80 and status in ("Pass", "Conditional"),
        }
    overall = all(g["gate_passed"] for g in per_rule.values()) if per_rule else False
    (output_dir / "quality_gates.json").write_text(
        json.dumps(
            {
                "gate_passed": overall,
                "per_rule_gates": per_rule,
                "score_mean": d.get("score_mean", 0.0),
                "rules_passed": d.get("rules_passed", 0),
                "total_rules": d.get("total_rules", 0),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_output(gen: ReportGenerator, output_dir: Optional[Path], fmt: str) -> None:
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        # Canonical Step08 file contract requires both summary artifacts whenever
        # an output directory is provided, regardless of CLI --format.
        (output_dir / "summary.json").write_text(gen.to_json(), encoding="utf-8")
        (output_dir / "summary.md").write_text(gen.to_markdown(), encoding="utf-8")
        _write_verification_json(gen, output_dir)
        _write_quality_gates_json(gen, output_dir)
    else:
        if fmt in ("json", "both"):
            print(gen.to_json())
        if fmt in ("markdown", "both"):
            print(gen.to_markdown())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate aggregate scoring report from per-rule scorecards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Input formats accepted by --input-scores:
  • Path to a .json file containing a JSON array, NDJSON, or object with
    a 'per_rule_scorecards' key
  • A raw JSON string (array or NDJSON)
  • Omit --input-scores to read NDJSON or JSON from stdin

Examples:
  # from file (JSON array or NDJSON)
  generate_report.py --input-scores scorecards.json --output-dir reports/ --format both

  # single rule piped as compact JSON
  score_rule.py --rule-id Rule-22 --verify-status pass --output-json | generate_report.py

  # multiple rules via NDJSON file
  generate_report.py --input-scores results.ndjson --format json
""",
    )
    parser.add_argument(
        "--input-scores",
        default=None,
        help="Path to scorecard file (JSON array / NDJSON) or raw JSON string. "
             "Omit to read from stdin.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
           help="Directory to write canonical Step08 report files: summary.json, summary.md, "
               "verification.json, quality_gates.json. Defaults to stdout.",
    )
    parser.add_argument(
        "--format",
        default="json",
        choices=("json", "markdown", "both"),
        help="Output format (default: json)",
    )

    args = parser.parse_args()

    gen = ReportGenerator()
    loaded_cards: List[Dict[str, Any]] = []

    if args.input_scores is not None:
        try:
            cards = _load_scorecards(args.input_scores)
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            print(f"Error loading scorecards: {exc}", file=sys.stderr)
            sys.exit(1)
        for card in cards:
            gen.add_scorecard(card)
            loaded_cards.append(card)
    else:
        # Read from stdin — accept JSON array, JSON object, or NDJSON
        raw = sys.stdin.read().strip()
        if not raw:
            print("Error: no input provided (use --input-scores or pipe scorecards to stdin)",
                  file=sys.stderr)
            sys.exit(1)
        try:
            cards = _load_scorecards(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"Error parsing stdin scorecards: {exc}", file=sys.stderr)
            sys.exit(1)
        for card in cards:
            gen.add_scorecard(card)
            loaded_cards.append(card)

    gen.finalize()

    if args.output_dir:
        base_dir = safe_path(args.output_dir)
        output_dir = _resolve_report_output_dir(base_dir, loaded_cards)
        _write_output(gen, output_dir, args.format)
        return

    # Default behavior: always write under ./output/reports/... for predictable artifacts.
    default_base = safe_path(Path.cwd() / "output")
    output_dir = _resolve_report_output_dir(default_base, loaded_cards)
    _write_output(gen, output_dir, args.format)

    # Preserve pipeline behavior by mirroring requested format to stdout.
    _emit_stdout(gen, args.format)


if __name__ == "__main__":
    main()
