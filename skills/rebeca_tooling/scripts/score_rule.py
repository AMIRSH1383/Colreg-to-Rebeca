#!/usr/bin/env python3
"""Score a single Legata→Rebeca translation against the 10-point TQC rubric.

Translation Quality Criteria (TQC) from docs/manuscript.tex §TQC:
  1. Syntax correctness   (0–1)  — automated via RMC two-stage exit code
  2. Attribute coverage   (0–3)  — automated via variable_map vs concept_mapping
  3. Actor coverage       (0–2)  — automated via actor_map vs concept_mapping
  4. No hallucinations    (0–1)  — auto-partial via stderr error patterns
  5. Logic granularity    (0–3)  — heuristic: define coverage + atomic proposition check
  Total max: 10 pts

The 10-pt total is always normalized to 0–100. When vacuity and/or mutation analyses
are enabled their results fill the remaining weight:

  Mode              | Base | Vacuity | Mutation
  Neither           | 100% |    —    |    —
  Vacuity only      |  85% |   15%   |    —
  Mutation only     |  75% |    —    |   25%
  Both              |  60% |   15%   |   25%
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Normalization weight constants (must sum to 100 for the "both enabled" mode)
# ---------------------------------------------------------------------------
_W_VACUITY: float = 15.0
_W_MUTATION: float = 25.0
_W_BASE_BOTH: float = 60.0
_W_BASE_VAC_ONLY: float = 85.0
_W_BASE_MUT_ONLY: float = 75.0
_W_BASE_NONE: float = 100.0

# ---------------------------------------------------------------------------
# Shared result type
# ---------------------------------------------------------------------------

@dataclass
class CriterionResult:
    score: int
    max_score: int
    method: str          # "automated" | "auto_partial" | "heuristic"
    detail: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        # Canonical output uses 'max' as the field name (not 'max_score')
        d = asdict(self)
        # map max_score -> max for backward compatibility with existing callers
        d['max'] = d.pop('max_score')
        return d


# ---------------------------------------------------------------------------
# Helper 1 — Syntax correctness (0–1)
# ---------------------------------------------------------------------------

_RMC_ERROR_LINE = re.compile(r"line:\d+,\s*column:\d+,\s*.+")


def score_syntax_correctness(
    rmc_exit_code: int,
    rmc_stderr_content: str = "",
    compile_stderr_content: str = "",
) -> CriterionResult:
    """Criterion 1: 1 if both compile stages passed, 0 otherwise."""
    if rmc_exit_code == 0:
        return CriterionResult(
            score=1, max_score=1, method="automated",
            detail={"stage_failed": None, "error_lines": []},
        )

    if rmc_exit_code == 5:
        error_lines = _RMC_ERROR_LINE.findall(rmc_stderr_content)
        return CriterionResult(
            score=0, max_score=1, method="automated",
            detail={"stage_failed": "rmc_parse", "error_lines": error_lines[:10]},
        )

    if rmc_exit_code == 4:
        cpp_errors = [
            ln.strip() for ln in compile_stderr_content.splitlines()
            if ": error:" in ln
        ][:10]
        return CriterionResult(
            score=0, max_score=1, method="automated",
            detail={"stage_failed": "cpp_compile", "error_lines": cpp_errors},
        )

    if rmc_exit_code == 3:
        return CriterionResult(
            score=0, max_score=1, method="automated",
            detail={"stage_failed": "rmc_timeout", "error_lines": []},
        )

    return CriterionResult(
        score=0, max_score=1, method="automated",
        detail={"stage_failed": "rmc_other", "error_lines": [], "exit_code": rmc_exit_code},
    )


# ---------------------------------------------------------------------------
# Helper 2 — Attribute coverage (0–3)
# ---------------------------------------------------------------------------

def score_attribute_coverage(
    variable_map: Dict[str, Any],
    concept_mapping: Dict[str, Any],
) -> CriterionResult:
    """Criterion 2: coverage of required attributes in mapping output (0–3)."""
    required: set = set(variable_map.keys())
    if not required:
        return CriterionResult(
            score=3, max_score=3, method="automated",
            detail={"required": [], "found": [], "missing": [], "coverage_pct": 100.0},
        )

    found: set = set()

    for patch in concept_mapping.get("statevar_patches", []):
        for sv in patch.get("add_statevars", []):
            found.add(sv.get("name", ""))

    for dp in concept_mapping.get("define_patches", []):
        expr = dp.get("expr", "")
        for var in required:
            if re.search(r"\b" + re.escape(var) + r"\b", expr):
                found.add(var)

    found = found & required
    missing = required - found
    coverage_pct = len(found) / len(required) * 100.0

    if coverage_pct < 33.0:
        score = 0
    elif coverage_pct < 67.0:
        score = 1
    elif coverage_pct < 100.0:
        score = 2
    else:
        score = 3

    return CriterionResult(
        score=score, max_score=3, method="automated",
        detail={
            "required": sorted(required),
            "found": sorted(found),
            "missing": sorted(missing),
            "coverage_pct": round(coverage_pct, 1),
        },
    )


# ---------------------------------------------------------------------------
# Helper 3 — Actor coverage (0–2)
# ---------------------------------------------------------------------------

def score_actor_coverage(
    actor_map: Dict[str, Any],
    concept_mapping: Dict[str, Any],
) -> CriterionResult:
    """Criterion 3: none/some/all relevant actors present in mapping (0–2)."""
    required: set = set(actor_map.keys())
    if not required:
        return CriterionResult(
            score=2, max_score=2, method="automated",
            detail={"required": [], "found": [], "missing": []},
        )

    found: set = set()
    for patch in (
        concept_mapping.get("statevar_patches", [])
        + concept_mapping.get("queue_size_patches", [])
    ):
        rc = patch.get("reactiveclass", "")
        if rc:
            found.add(rc)

    found = found & required
    missing = required - found

    if not found:
        score = 0
    elif found < required:
        score = 1
    else:
        score = 2

    return CriterionResult(
        score=score, max_score=2, method="automated",
        detail={
            "required": sorted(required),
            "found": sorted(found),
            "missing": sorted(missing),
        },
    )


# ---------------------------------------------------------------------------
# Helper 4 — No hallucinations (0–1)
# ---------------------------------------------------------------------------

_HALLUCINATION_RMC = re.compile(
    r"undefined|not declared|unknown symbol|cannot resolve|unresolved",
    re.IGNORECASE,
)

_HALLUCINATION_CPP = re.compile(
    r"has no member named|was not declared in this scope|is not a member of|no such identifier",
    re.IGNORECASE,
)


def score_hallucination_free(
    rmc_exit_code: int,
    rmc_stderr_content: str = "",
    compile_stderr_content: str = "",
) -> CriterionResult:
    """Criterion 4: 1 if no fictitious references detected, 0 otherwise."""
    if rmc_exit_code == 0:
        return CriterionResult(
            score=1, max_score=1, method="auto_partial",
            detail={"matched_patterns": [], "stage": "clean"},
        )

    rmc_matches = _HALLUCINATION_RMC.findall(rmc_stderr_content)
    cpp_matches = _HALLUCINATION_CPP.findall(compile_stderr_content)

    if rmc_matches:
        return CriterionResult(
            score=0, max_score=1, method="auto_partial",
            detail={"matched_patterns": list(set(rmc_matches)), "stage": "rmc_parse"},
        )
    if cpp_matches:
        return CriterionResult(
            score=0, max_score=1, method="auto_partial",
            detail={"matched_patterns": list(set(cpp_matches)), "stage": "cpp_compile"},
        )

    return CriterionResult(
        score=0, max_score=1, method="auto_partial",
        detail={"matched_patterns": [], "stage": "syntax_or_other_error"},
    )


# ---------------------------------------------------------------------------
# Helper 5 — Logic correctness (0–2)
# ---------------------------------------------------------------------------

def _parse_define_props(property_text: str) -> Dict[str, str]:
    """Return {prop_name: rhs_expr} for every entry in the define block."""
    m = re.search(r'\bdefine\s*\{([^}]*)\}', property_text, re.DOTALL)
    if not m:
        return {}
    props: Dict[str, str] = {}
    for entry in m.group(1).split(';'):
        entry = entry.strip()
        if '=' not in entry:
            continue
        name, _, rhs = entry.partition('=')
        name = name.strip()
        if name:
            props[name] = rhs.strip()
    return props


def _parse_assertion_block(property_text: str) -> str:
    """Return the raw text inside Assertion { ... }."""
    m = re.search(r'\bAssertion\s*\{([^}]*)\}', property_text, re.DOTALL)
    return m.group(1) if m else ""


def _check_expression_complete(
    props: Dict[str, str], assertion_block: str
) -> Tuple[int, Dict[str, Any]]:
    if not props:
        return 0, {"defined": [], "used": [], "unused": [], "note": "no define block"}
    unused = [
        name for name in props
        if not re.search(r'\b' + re.escape(name) + r'\b', assertion_block)
    ]
    score = 1 if not unused else 0
    return score, {
        "defined": sorted(props.keys()),
        "used": sorted(set(props.keys()) - set(unused)),
        "unused": sorted(unused),
    }


_COMPOUND_OP = re.compile(r'\&\&|\|\|')


def _check_semantic_correct(props: Dict[str, str]) -> Tuple[int, Dict[str, Any]]:
    if not props:
        return 0, {"compound_props": [], "note": "no define block"}
    compound = [name for name, rhs in props.items() if _COMPOUND_OP.search(rhs)]
    score = 2 if not compound else 0
    return score, {"compound_props": sorted(compound)}


def score_logic_granularity_correctness(
    property_text: str,
) -> CriterionResult:
    """Criterion 5: expression completeness + semantic correctness (0–2).

    Expression completeness (1 pt): every prop in define{} appears in Assertion{}.
    Semantic correctness (2 pt): no prop in define{} is compound (no && or || in
    RHS), ensuring each atomic proposition maps to a single state comparison so
    counterexample traces identify exactly which proposition failed.
    Both are static analyses of property_text only.
    """
    props = _parse_define_props(property_text)
    assertion_block = _parse_assertion_block(property_text)

    expr_score, expr_detail = _check_expression_complete(props, assertion_block)
    sem_score, sem_detail = _check_semantic_correct(props)

    return CriterionResult(
        score=expr_score + sem_score,
        max_score=3,
        method="heuristic",
        detail={
            "expression_complete": expr_score,
            "semantic_correct": sem_score,
            "expression_detail": expr_detail,
            "semantic_detail": sem_detail,
        },
    )


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

class RubricScorer:
    """TQC 10-point rubric scorer, normalized to 0–100."""

    def score_rule(
        self,
        rule_id: str,
        verify_status: str = "unknown",
        rmc_exit_code: Optional[int] = None,
        model_outcome: Optional[str] = None,
        is_vacuous: Optional[bool] = None,
        assertion_id: Optional[str] = None,
        mutation_score: Optional[float] = None,
        property_text: str = "",
        variable_map: Optional[Dict[str, Any]] = None,
        actor_map: Optional[Dict[str, Any]] = None,
        concept_mapping: Optional[Dict[str, Any]] = None,
        rmc_stderr_content: str = "",
        compile_stderr_content: str = "",
    ) -> Dict[str, Any]:
        """Score a single rule translation. Returns scorecard dict."""
        effective_status = verify_status
        if rmc_exit_code is not None and rmc_exit_code != 0:
            effective_status = "fail"
        elif (model_outcome or "").strip().lower() == "cex":
            effective_status = "fail"

        exit_code = rmc_exit_code if rmc_exit_code is not None else (0 if effective_status == "pass" else 1)

        vacuity_entry: Dict[str, Any] = {
            "is_vacuous": is_vacuous,
            "assertion_id": assertion_id,
            "status": (
                "vacuous" if is_vacuous is True
                else "non_vacuous" if is_vacuous is False
                else "unchecked"
            ),
        }

        bounded_mutation: Optional[float] = (
            max(0.0, min(100.0, float(mutation_score)))
            if mutation_score is not None else None
        )

        # Run all 5 TQC helpers
        c1 = score_syntax_correctness(exit_code, rmc_stderr_content, compile_stderr_content)
        c2 = score_attribute_coverage(variable_map or {}, concept_mapping or {})
        c3 = score_actor_coverage(actor_map or {}, concept_mapping or {})
        c4 = score_hallucination_free(exit_code, rmc_stderr_content, compile_stderr_content)
        c5 = score_logic_granularity_correctness(property_text)

        rubric_total = c1.score + c2.score + c3.score + c4.score + c5.score

        rubric_10pt = {
            "syntax_correctness": c1.to_dict(),
            "attribute_coverage": c2.to_dict(),
            "actor_coverage":     c3.to_dict(),
            "hallucination_free": c4.to_dict(),
            "logic_correctness":  c5.to_dict(),
            "total": rubric_total,
            "max":   10,
        }

        has_vacuity  = is_vacuous is not None
        has_mutation = bounded_mutation is not None

        if has_vacuity and has_mutation:
            base_weight = _W_BASE_BOTH
        elif has_vacuity:
            base_weight = _W_BASE_VAC_ONLY
        elif has_mutation:
            base_weight = _W_BASE_MUT_ONLY
        else:
            base_weight = _W_BASE_NONE

        base_pct     = (rubric_total / 10.0) * base_weight
        vacuity_pct  = (_W_VACUITY if is_vacuous is not True else 0.0) if has_vacuity else 0.0
        mutation_pct = ((bounded_mutation / 100.0) * _W_MUTATION) if has_mutation else 0.0
        score_total  = round(base_pct + vacuity_pct + mutation_pct)

        failure_reasons: List[str] = []
        remediation_hints: List[str] = []

        if effective_status == "pass":
            status = "Pass"
            confidence = round(0.8 + 0.1 * (rubric_total / 10.0), 2)
            if is_vacuous is True:
                status = "Conditional"
                confidence = 0.6
                failure_reasons.append("Property verified but vacuously — precondition never reachable")
                remediation_hints.append("Review precondition reachability; strengthen model state space")
        elif effective_status == "fail":
            status = "Fail"
            confidence = 0.5
            if rmc_exit_code and rmc_exit_code != 0:
                failure_reasons.append(f"Verification failed in RMC model checker (exit={rmc_exit_code})")
            elif (model_outcome or "").strip().lower() == "cex":
                failure_reasons.append("model.out reported counterexample outcome (cex)")
            else:
                failure_reasons.append("Verification failed in RMC model checker")
            remediation_hints += [
                "Review counterexample from RMC output",
                "Check state variable alignment",
                "Verify assertion logic matches Legata condition",
            ]
        elif effective_status == "timeout":
            status = "Conditional"
            confidence = 0.3
            failure_reasons.append("Verification timed out (>120s)")
            remediation_hints += [
                "Increase timeout in rmc_config",
                "Simplify actor state space",
                "Review property complexity",
            ]
        elif verify_status == "blocked":
            status = "Blocked"
            confidence = 0.0
            failure_reasons.append("Legata formalization insufficient")
            remediation_hints += ["Use COLREG fallback mapping", "Manual review required"]
        else:
            status = "Unknown"
            confidence = 0.0
            failure_reasons.append("Verification status unknown")

        if c1.score == 0:
            failure_reasons.append(f"Syntax error in stage: {c1.detail.get('stage_failed')}")
        if c2.score < 2:
            missing = c2.detail.get("missing", [])
            if missing:
                failure_reasons.append(f"Missing attributes in mapping: {missing}")
        if c3.score < 2:
            missing = c3.detail.get("missing", [])
            if missing:
                failure_reasons.append(f"Missing actors in mapping: {missing}")
        if c4.score == 0 and c4.detail.get("matched_patterns"):
            failure_reasons.append(f"Hallucination detected: {c4.detail['matched_patterns']}")
        if c5.detail.get("expression_complete") == 0:
            failure_reasons.append("Assertion form missing or malformed in property file")

        return {
            "rule_id": rule_id,
            "rubric_10pt": rubric_10pt,
            "score_breakdown": {
                "base_10pt":      rubric_total,
                "base_10pt_pct":  round(base_pct, 2),
                "vacuity_pct":   round(vacuity_pct, 2) if has_vacuity else None,
                "mutation_pct":  round(mutation_pct, 2) if has_mutation else None,
            },
            "score_total": score_total,
            "status": status,
            "confidence": confidence,
            "vacuity": vacuity_entry,
            "mutation_score": bounded_mutation if bounded_mutation is not None else 0.0,
            "rmc_exit_code": rmc_exit_code,
            "model_outcome": (model_outcome or "unknown").strip().lower(),
            "mapping_path": "legata",
            "failure_reasons": failure_reasons,
            "remediation_hints": remediation_hints,
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Score a single Legata→Rebeca translation (TQC 10-pt rubric)"
    )
    parser.add_argument("--rule-id", required=True)
    parser.add_argument("--verify-status", default="unknown",
                        choices=["pass", "fail", "timeout", "blocked", "unknown"])
    parser.add_argument("--rmc-exit-code", type=int, default=None)
    parser.add_argument("--model-outcome", default="unknown",
                        choices=["satisfied", "cex", "unknown"])
    parser.add_argument("--is-vacuous", default=None, choices=["true", "false"],
                        help="Vacuity result (omit if vacuity was not run)")
    parser.add_argument("--assertion-id", default=None)
    parser.add_argument("--mutation-score", type=float, default=None,
                        help="Mutation kill rate [0,100] (omit if mutation was not run)")
    parser.add_argument("--vacuity-comparison", default="unknown",
                        choices=["same", "changed", "unknown"])
    parser.add_argument("--output-dir", default="output",
                        help="Pipeline base output directory (default: output). "
                             "All input artifact paths are resolved from here via output_policy. "
                             "Output artifact written to <output-dir>/work/<rule-id>/step07_reporting.json.")
    parser.add_argument("--output-json", action="store_true")
    parser.add_argument("--output-file", metavar="PATH", default=None)

    args = parser.parse_args()

    is_vacuous: Optional[bool] = None
    if args.is_vacuous == "true":
        is_vacuous = True
    elif args.is_vacuous == "false":
        is_vacuous = False

    # Bootstrap package root so sibling imports work when run directly
    _HERE = Path(__file__).resolve().parent
    _PKG_ROOT = _HERE.parent.parent.parent
    if str(_PKG_ROOT) not in sys.path:
        sys.path.insert(0, str(_PKG_ROOT))
    from skills.rebeca_tooling.scripts.output_policy import (
        step_artifact_path, final_paths, verification_paths,
    )
    from skills.rebeca_tooling.scripts.artifact_writer import _atomic_write

    base = Path(args.output_dir)
    rule_id = args.rule_id

    def _read(p: Path) -> str:
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def _read_json(p: Path) -> Dict[str, Any]:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    property_file  = final_paths(rule_id, base).property
    abs_path       = step_artifact_path(rule_id, "step02_abstraction", base)
    cm_path        = step_artifact_path(rule_id, "step03_mapping", base)
    rmc_dir        = verification_paths(rule_id, run_id="current", base_dir=base).rule_verification_dir / "rmc"

    abs_raw  = _read_json(abs_path)
    abs_data = abs_raw.get("abstraction_summary", abs_raw)

    cm_raw  = _read_json(cm_path)
    cm_data = cm_raw.get("concept_mapping", cm_raw)

    scorer = RubricScorer()
    scorecard = scorer.score_rule(
        rule_id=rule_id,
        verify_status=args.verify_status,
        rmc_exit_code=args.rmc_exit_code,
        model_outcome=args.model_outcome,
        is_vacuous=is_vacuous,
        assertion_id=args.assertion_id,
        mutation_score=args.mutation_score,
        property_text=_read(property_file),
        variable_map=abs_data.get("variable_map", {}),
        actor_map=abs_data.get("actor_map", {}),
        concept_mapping=cm_data,
        rmc_stderr_content=_read(rmc_dir / "rmc_stderr.log"),
        compile_stderr_content=_read(rmc_dir / "compile_stderr.log"),
    )

    # Always write the canonical pipeline artifact
    artifact_path = step_artifact_path(rule_id, "step07_reporting", base)
    _atomic_write(artifact_path, scorecard)

    if args.output_file:
        _atomic_write(Path(args.output_file), scorecard)

    if args.output_json:
        print(json.dumps(scorecard, indent=2))
    elif not args.output_file:
        r = scorecard["rubric_10pt"]
        print(f"Rule:        {scorecard['rule_id']}")
        print(f"Status:      {scorecard['status']}")
        print(f"Score:       {scorecard['score_total']}/100")
        print(f"Rubric:      {r['total']}/{r['max']} pts")
        print(f"Confidence:  {scorecard['confidence']:.1%}")
        print("\nTQC Breakdown:")
        for name, c in [
            ("1. Syntax",     r["syntax_correctness"]),
            ("2. Attributes", r["attribute_coverage"]),
            ("3. Actors",     r["actor_coverage"]),
            ("4. No halluc.", r["hallucination_free"]),
            ("5. Logic",      r["logic_correctness"]),
        ]:
            print(f"  {name}: {c['score']}/{c['max']}  [{c['method']}]")
        if scorecard["failure_reasons"]:
            print("\nIssues:")
            for reason in scorecard["failure_reasons"]:
                print(f"  - {reason}")


if __name__ == "__main__":
    main()
