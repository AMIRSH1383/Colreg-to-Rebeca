#!/usr/bin/env python3
"""Shared helpers for comprehensive per-rule and consolidated reporting."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple



@dataclass(frozen=True)
class RuleReportBundle:
    """Normalized per-rule report payload used by consolidation tooling."""

    rule_id: str
    folder: str
    status: str
    score_total: float
    score_breakdown: Dict[str, float]
    failure_reasons: List[str]
    remediation_hints: List[str]
    mutation: Dict[str, Any]
    vacuity: Dict[str, Any]
    model_property_stats: Dict[str, Any]
    mapping_delta: Dict[str, Optional[int]]
    artifacts: Dict[str, str]
    rubric_10pt: Dict[str, Any]


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    decoder = json.JSONDecoder()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        pass

    # Recovery path for polluted files where log lines were prefixed before JSON.
    # We decode from the first "{" / "[" token and keep the first dict payload.
    try:
        raw = path.read_text(encoding="utf-8")
        for idx, ch in enumerate(raw):
            if ch not in "[{":
                continue
            try:
                data, _ = decoder.raw_decode(raw[idx:])
            except Exception:
                continue
            if isinstance(data, dict):
                return data
    except Exception:
        return None
    return None


def _find_first_json(rule_dir: Path, pattern: str) -> Optional[Path]:
    matches = sorted(rule_dir.glob(pattern))
    return matches[0] if matches else None


def _extract_rule_id(scorecard: Dict[str, Any], folder_name: str) -> str:
    rid = scorecard.get("rule_id")
    if isinstance(rid, str) and rid.strip():
        return rid.strip()
    m = re.search(r"(Rule[-_ ]?\d+)", folder_name, re.IGNORECASE)
    if m:
        return m.group(1).replace("_", "-").replace(" ", "-")
    return folder_name


def _extract_mutation_metrics(
    candidates_json: Optional[Dict[str, Any]],
    killrun_json: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    generated_total = 0
    if candidates_json:
        generated_total = int(candidates_json.get("total_mutants", 0) or 0)

    sampled_total = None
    population_total = 0
    executed_total = 0
    killed_total = 0
    survived_total = 0
    errors_total = 0
    mutation_score = None

    if killrun_json:
        kill_stats = killrun_json.get("kill_stats")
        if not isinstance(kill_stats, dict):
            kill_stats = killrun_json
        if isinstance(kill_stats, dict):
            population_total = int(kill_stats.get("total_generated", 0) or 0)
            executed_total = int(kill_stats.get("total_run", 0) or 0)
            killed_total = int(kill_stats.get("killed", 0) or 0)
            survived_total = int(kill_stats.get("survived", 0) or 0)
            errors_total = int(kill_stats.get("errors", 0) or 0)
            sampled_flag = bool(kill_stats.get("sampled", False))
            sampled_total = executed_total if sampled_flag else (population_total if population_total > 0 else None)
            raw_score = kill_stats.get("mutation_score")
            try:
                mutation_score = float(raw_score) if raw_score is not None else None
            except (TypeError, ValueError):
                mutation_score = None

    if generated_total == 0 and population_total > 0:
        generated_total = population_total

    return {
        "mutants_generated_total": generated_total,
        "mutants_selected_total": sampled_total,
        "mutants_executed_total": executed_total,
        "mutants_killed_total": killed_total,
        "mutants_survived_total": survived_total,
        "mutants_error_total": errors_total,
        "mutation_score": mutation_score,
    }


def _extract_vacuity_metrics(vacuity_jsons: List[Tuple[Path, Dict[str, Any]]]) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    vacuous_count = 0
    non_vacuous_count = 0
    unknown_count = 0

    for path, payload in vacuity_jsons:
        is_vacuous = payload.get("is_vacuous")
        if is_vacuous is True:
            vacuous_count += 1
        elif is_vacuous is False:
            non_vacuous_count += 1
        else:
            unknown_count += 1

        checks.append(
            {
                "file": str(path),
                "assertion_id": payload.get("assertion_id_used"),
                "is_vacuous": is_vacuous,
                "comparison_basis": payload.get("comparison_basis"),
                "baseline_outcome": payload.get("baseline_outcome"),
                "secondary_outcome": payload.get("secondary_outcome"),
                "secondary_exit_code": payload.get("secondary_exit_code"),
                "explanation": payload.get("explanation"),
            }
        )

    overall = "unknown"
    if vacuous_count > 0:
        overall = "vacuous"
    elif non_vacuous_count > 0 and unknown_count == 0:
        overall = "non_vacuous"

    return {
        "checks": checks,
        "checks_total": len(checks),
        "checks_vacuous": vacuous_count,
        "checks_non_vacuous": non_vacuous_count,
        "checks_unknown": unknown_count,
        "overall": overall,
    }


def _extract_vacuity_from_scorecard(scorecard: Dict[str, Any]) -> Dict[str, Any]:
    vacuity = scorecard.get("vacuity")
    if not isinstance(vacuity, dict):
        return {
            "checks": [],
            "checks_total": 0,
            "checks_vacuous": 0,
            "checks_non_vacuous": 0,
            "checks_unknown": 0,
            "overall": "unknown",
        }

    is_vacuous = vacuity.get("is_vacuous")
    if is_vacuous is True:
        overall = "vacuous"
        vacuous_count = 1
        non_vacuous_count = 0
        unknown_count = 0
    elif is_vacuous is False:
        overall = "non_vacuous"
        vacuous_count = 0
        non_vacuous_count = 1
        unknown_count = 0
    else:
        overall = "unknown"
        vacuous_count = 0
        non_vacuous_count = 0
        unknown_count = 1

    return {
        "checks": [
            {
                "file": "scorecard.vacuity",
                "assertion_id": vacuity.get("assertion_id"),
                "is_vacuous": is_vacuous,
                "comparison_basis": "scorecard",
                "baseline_outcome": None,
                "secondary_outcome": None,
                "secondary_exit_code": None,
                "explanation": vacuity.get("status"),
            }
        ],
        "checks_total": 1,
        "checks_vacuous": vacuous_count,
        "checks_non_vacuous": non_vacuous_count,
        "checks_unknown": unknown_count,
        "overall": overall,
    }


def _count_define_predicates(property_content: str) -> int:
    define_match = re.search(r"\bdefine\s*\{([^}]*)\}", property_content, re.DOTALL)
    if not define_match:
        return 0
    block = define_match.group(1)
    entries = [line for line in block.split(";") if "=" in line]
    return len(entries)


def _count_assertions(property_content: str) -> int:
    assertion_match = re.search(r"\bAssertion\s*\{([^}]*)\}", property_content, re.DOTALL)
    if not assertion_match:
        return 0
    block = assertion_match.group(1)
    return len(re.findall(r"\b\w+\s*:\s*.+?;", block, re.DOTALL))


def _count_statevars(model_content: str) -> int:
    count = 0
    for block in re.findall(r'\bstatevars\s*\{([^}]*)\}', model_content, re.DOTALL):
        count += len(re.findall(r'\b\w+\s+\w+\s*(?:=\s*[^;]+)?\s*;', block))
    return count


def _extract_model_property_stats(model_file: Optional[Path], property_file: Optional[Path]) -> Dict[str, Any]:
    statevars_count = 0
    predicates_count = 0
    assertions_count = 0

    if model_file and model_file.exists():
        try:
            model_content = model_file.read_text(encoding="utf-8")
            statevars_count = _count_statevars(model_content)
        except Exception:
            statevars_count = 0

    if property_file and property_file.exists():
        try:
            prop_content = property_file.read_text(encoding="utf-8")
            predicates_count = _count_define_predicates(prop_content)
            assertions_count = _count_assertions(prop_content)
        except Exception:
            predicates_count = 0
            assertions_count = 0

    return {
        "statevars_count": statevars_count,
        "predicates_count": predicates_count,
        "assertions_count": assertions_count,
    }


def _extract_mapping_delta(rule_dir: Path) -> Dict[str, Optional[int]]:
    """
    Read optional mapping delta stats when present.

    Expected file: mapping_delta.json with keys like
      statevars_added/refined, predicates_added/refined, assertions_added/refined.
    """
    path = rule_dir / "mapping_delta.json"
    payload = _load_json(path) if path.exists() else None
    keys = (
        "statevars_added",
        "statevars_refined",
        "predicates_added",
        "predicates_refined",
        "assertions_added",
        "assertions_refined",
    )
    if not payload:
        return {k: None for k in keys}

    out: Dict[str, Optional[int]] = {}
    for key in keys:
        val = payload.get(key)
        try:
            out[key] = int(val) if val is not None else None
        except (TypeError, ValueError):
            out[key] = None
    return out


def build_rule_report_bundle(rule_dir: Path) -> Optional[RuleReportBundle]:
    """Collect known artifacts under one rule folder and normalize report fields."""
    scorecard_path = _find_first_json(rule_dir, "scorecard*.json")
    if scorecard_path is None:
        scorecard_path = _find_first_json(rule_dir, "*score*.json")
    if scorecard_path is None:
        return None

    scorecard = _load_json(scorecard_path)
    if not scorecard:
        return None

    candidates_path = rule_dir / "mutation_candidates.json"
    killrun_path = rule_dir / "mutation_killrun.json"

    candidates_json = _load_json(candidates_path) if candidates_path.exists() else None
    killrun_json = _load_json(killrun_path) if killrun_path.exists() else None

    vacuity_jsons: List[Tuple[Path, Dict[str, Any]]] = []
    for path in sorted(rule_dir.glob("vacuity*.json")):
        payload = _load_json(path)
        if payload:
            vacuity_jsons.append((path, payload))

    model_file = next(iter(sorted((rule_dir / "model").glob("*.rebeca"))), None) if (rule_dir / "model").exists() else None
    property_file = next(iter(sorted((rule_dir / "property").glob("*.property"))), None) if (rule_dir / "property").exists() else None

    status = str(scorecard.get("status", "Unknown"))
    score_total_raw = scorecard.get("score_total", 0)
    try:
        score_total = float(score_total_raw)
    except (TypeError, ValueError):
        score_total = 0.0

    score_breakdown_raw = scorecard.get("score_breakdown", {})
    score_breakdown: Dict[str, float] = {}
    if isinstance(score_breakdown_raw, dict):
        for k, v in score_breakdown_raw.items():
            try:
                score_breakdown[str(k)] = float(v)
            except (TypeError, ValueError):
                score_breakdown[str(k)] = 0.0

    vacuity_metrics = _extract_vacuity_metrics(vacuity_jsons)
    if vacuity_metrics.get("checks_total", 0) == 0:
        vacuity_metrics = _extract_vacuity_from_scorecard(scorecard)

    rubric_10pt_raw = scorecard.get("rubric_10pt", {})
    rubric_10pt: Dict[str, Any] = rubric_10pt_raw if isinstance(rubric_10pt_raw, dict) else {}

    return RuleReportBundle(
        rule_id=_extract_rule_id(scorecard, rule_dir.name),
        folder=str(rule_dir),
        status=status,
        score_total=score_total,
        score_breakdown=score_breakdown,
        failure_reasons=[str(x) for x in scorecard.get("failure_reasons", [])],
        remediation_hints=[str(x) for x in scorecard.get("remediation_hints", [])],
        mutation=_extract_mutation_metrics(candidates_json, killrun_json),
        vacuity=vacuity_metrics,
        model_property_stats=_extract_model_property_stats(model_file, property_file),
        mapping_delta=_extract_mapping_delta(rule_dir),
        artifacts={
            "scorecard": str(scorecard_path),
            "mutation_candidates": str(candidates_path) if candidates_path.exists() else "",
            "mutation_killrun": str(killrun_path) if killrun_path.exists() else "",
            "model": str(model_file) if model_file else "",
            "property": str(property_file) if property_file else "",
        },
        rubric_10pt=rubric_10pt,
    )


def summarize_status_counts(bundles: List[RuleReportBundle]) -> Dict[str, int]:
    counts = {"Pass": 0, "Fail": 0, "Conditional": 0, "Blocked": 0, "Unknown": 0}
    for b in bundles:
        key = b.status if b.status in counts else "Unknown"
        counts[key] += 1
    return counts
