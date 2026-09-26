"""Tests for reporting_metrics helpers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from skills.rebeca_tooling.scripts.reporting_metrics import build_rule_report_bundle


MODEL_TEXT = """\
reactiveclass Ship(5) {
  statevars {
    int length;
    boolean hasLight;
  }
}
main { Ship s():(); }
"""

PROPERTY_TEXT = """\
property {
  define {
    isLong = (s.length > 50);
    hasLightOn = (s.hasLight == true);
  }
  Assertion {
    Rule22: !isLong || hasLightOn;
  }
}
"""


def test_build_rule_report_bundle_extracts_metrics() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        rule_dir = Path(td) / "rule22"
        (rule_dir / "model").mkdir(parents=True)
        (rule_dir / "property").mkdir(parents=True)

        (rule_dir / "scorecard_Rule-22.json").write_text(
            json.dumps(
                {
                    "rule_id": "Rule-22",
                    "status": "Conditional",
                    "score_total": 85,
                    "score_breakdown": {"syntax": 10, "semantic_alignment": 55},
                    "failure_reasons": ["vacuous"],
                    "remediation_hints": ["improve reachability"],
                }
            ),
            encoding="utf-8",
        )
        (rule_dir / "mutation_candidates.json").write_text(
            json.dumps({"total_mutants": 246}), encoding="utf-8"
        )
        (rule_dir / "mutation_killrun.json").write_text(
            json.dumps(
                {
                    "kill_stats": {
                        "total_generated": 40,
                        "total_run": 40,
                        "killed": 12,
                        "survived": 26,
                        "errors": 2,
                        "mutation_score": 30.0,
                    }
                }
            ),
            encoding="utf-8",
        )
        (rule_dir / "vacuity_rule22.json").write_text(
            json.dumps(
                {
                    "assertion_id_used": "Rule22",
                    "is_vacuous": True,
                    "comparison_basis": "semantic_outcome",
                    "baseline_outcome": "satisfied",
                    "secondary_outcome": "satisfied",
                    "secondary_exit_code": 0,
                    "explanation": "VACUOUS",
                }
            ),
            encoding="utf-8",
        )
        (rule_dir / "model" / "SimulationModelCode.rebeca").write_text(MODEL_TEXT, encoding="utf-8")
        (rule_dir / "property" / "SimulationModelCode.property").write_text(PROPERTY_TEXT, encoding="utf-8")

        bundle = build_rule_report_bundle(rule_dir)

    assert bundle is not None
    assert bundle.rule_id == "Rule-22"
    assert bundle.mutation["mutants_generated_total"] == 246
    assert bundle.mutation["mutants_executed_total"] == 40
    assert bundle.mutation["mutants_killed_total"] == 12
    assert bundle.vacuity["checks_total"] == 1
    assert bundle.vacuity["checks_vacuous"] == 1
    assert bundle.model_property_stats["statevars_count"] == 2
    assert bundle.model_property_stats["predicates_count"] == 2
    assert bundle.model_property_stats["assertions_count"] == 1


def test_build_rule_report_bundle_recovers_noisy_killrun_json() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        rule_dir = Path(td) / "rule22"
        (rule_dir / "model").mkdir(parents=True)
        (rule_dir / "property").mkdir(parents=True)

        (rule_dir / "scorecard_Rule-22.json").write_text(
            json.dumps(
                {
                    "rule_id": "Rule-22",
                    "status": "Conditional",
                    "score_total": 85,
                    "score_breakdown": {"syntax": 10, "semantic_alignment": 55},
                    "vacuity": {
                        "is_vacuous": True,
                        "assertion_id": "Rule22",
                        "status": "vacuous",
                    },
                }
            ),
            encoding="utf-8",
        )
        (rule_dir / "mutation_candidates.json").write_text(
            json.dumps({"total_mutants": 328}), encoding="utf-8"
        )

        noisy = (
            "Executing RMC...\n"
            "✓ Phase 1\n"
            + json.dumps(
                {
                    "mode": "kill_run",
                    "rule_id": "Rule-22",
                    "kill_stats": {
                        "total_generated": 723,
                        "sampled": True,
                        "total_run": 40,
                        "killed": 12,
                        "survived": 26,
                        "errors": 2,
                        "mutation_score": 30.0,
                    },
                }
            )
        )
        (rule_dir / "mutation_killrun.json").write_text(noisy, encoding="utf-8")
        (rule_dir / "model" / "SimulationModelCode.rebeca").write_text(MODEL_TEXT, encoding="utf-8")
        (rule_dir / "property" / "SimulationModelCode.property").write_text(PROPERTY_TEXT, encoding="utf-8")

        bundle = build_rule_report_bundle(rule_dir)

    assert bundle is not None
    assert bundle.mutation["mutants_generated_total"] == 328
    assert bundle.mutation["mutants_selected_total"] == 40
    assert bundle.mutation["mutants_executed_total"] == 40
    assert bundle.mutation["mutants_killed_total"] == 12
    assert bundle.mutation["mutation_score"] == 30.0
    assert bundle.vacuity["checks_total"] == 1
    assert bundle.vacuity["overall"] == "vacuous"
