"""Single-invocation verification gate: RMC → vacuity → mutation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Ensure package root is on sys.path when run directly
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_PKG_ROOT = _HERE.parent.parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from skills.rebeca_tooling.scripts.run_rmc import run_rmc_detailed
from skills.rebeca_tooling.scripts.vacuity_checker import check_vacuity
from skills.rebeca_tooling.scripts.mutation_engine import (
    MutationEngine,
    run_mutants,
    write_mutation_artifact,
)
from skills.rebeca_tooling.scripts.utils import safe_path
from skills.rebeca_tooling.scripts.output_policy import step_artifact_path

_MUTATION_SCORE_THRESHOLD = 80.0


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def run_verification_gate(
    jar: str,
    model: str,
    property_file: str,
    rule_id: str,
    output_dir: str,
    rmc_timeout: int = 120,
    vacuity_timeout: int = 60,
    max_mutants: int = 50,
    mutation_timeout: int = 600,
    seed: int = 42,
    skip_vacuity: bool = False,
    skip_mutation: bool = False,
) -> Dict[str, Any]:
    """Run RMC, vacuity, and mutation and return all results in one dict.

    All three phases always run when the model is parseable (RMC exit 0).
    Vacuity result does not gate mutation — the agent gets the full picture
    in a single call and decides what to fix.
    Vacuity and mutation are skipped only when RMC itself fails (unparseable
    model/property), since both depend on a working model.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Phase 0 — RMC
    # ------------------------------------------------------------------
    rmc_result = run_rmc_detailed(
        jar=jar,
        model=model,
        property_file=property_file,
        output_dir=str(out / "rmc"),
        timeout_seconds=rmc_timeout,
        run_model_outcome=True,
    )

    exit_code: int = rmc_result.get("rmc_exit_code", 0)
    verified: bool = rmc_result.get("rmc_outcome") == "verified"

    payload: Dict[str, Any] = {
        "verified": verified,
        "rmc_exit_code": exit_code,
        "rmc_details": rmc_result,
        "vacuity_status": None,
        "mutation_score": None,
        "mutation_details": None,
        "passes_gate": False,
    }

    if not verified:
        # Vacuity and mutation require a parseable model — skip both.
        return payload

    # ------------------------------------------------------------------
    # Phase 1 — Vacuity
    # ------------------------------------------------------------------
    is_vacuous: Optional[bool] = False
    if not skip_vacuity:
        vacuity_result = check_vacuity(
            jar=jar,
            model=model,
            property_file=property_file,
            output_dir=str(out / "vacuity"),
            timeout_seconds=vacuity_timeout,
            assertion_id=rule_id,
            rule_id=rule_id,
        )
        payload["vacuity_status"] = vacuity_result
        is_vacuous = vacuity_result.get("is_vacuous")

    # ------------------------------------------------------------------
    # Phase 2 — Mutation (always runs when model is parseable)
    # ------------------------------------------------------------------
    if not skip_mutation:
        engine = MutationEngine()
        model_content = Path(model).read_text(encoding="utf-8")
        prop_content = Path(property_file).read_text(encoding="utf-8")

        mutations = (
            engine.mutate_model(model_content, rule_id)
            + engine.mutate_property(prop_content, rule_id)
        )

        kill_stats = run_mutants(
            mutations=mutations,
            jar=jar,
            model_path=Path(model),
            property_path=Path(property_file),
            timeout_seconds=60,
            max_mutants=max_mutants,
            total_timeout=mutation_timeout,
            seed=seed,
        )

        mutation_out = out / "mutation_killrun.json"
        write_mutation_artifact(mutation_out, kill_stats)

        score: float = kill_stats.get("mutation_score", 0.0)
        payload["mutation_score"] = score
        payload["mutation_details"] = kill_stats
    else:
        score = 0.0

    # ------------------------------------------------------------------
    # Gate result
    # ------------------------------------------------------------------
    payload["passes_gate"] = (
        verified
        and not is_vacuous
        and (skip_mutation or score >= _MUTATION_SCORE_THRESHOLD)
    )

    return payload


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _write_atomic(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RMC + vacuity + mutation in one call"
    )
    parser.add_argument("--jar",        required=True, help="Path to rmc.jar")
    parser.add_argument("--model",      required=True, help="Path to .rebeca file")
    parser.add_argument("--property",   required=True, help="Path to .property file")
    parser.add_argument("--rule-id",    required=True, help="Rule identifier (e.g. Rule-22)")
    parser.add_argument("--output-dir", required=True, help="Directory for verification artefacts")
    parser.add_argument("--base-dir",   default="output", help="Pipeline base dir for artifact_writer (default: output)")
    parser.add_argument("--output-file", metavar="PATH", help="Also write JSON result atomically to PATH")
    parser.add_argument("--output-json", action="store_true", help="Print JSON result to stdout")
    parser.add_argument("--rmc-timeout",      type=int, default=120)
    parser.add_argument("--vacuity-timeout",  type=int, default=60)
    parser.add_argument("--max-mutants",      type=int, default=50)
    parser.add_argument("--mutation-timeout", type=int, default=600)
    parser.add_argument("--seed",             type=int, default=42)

    parser.add_argument("--vacuity",    dest="vacuity", action="store_true",  default=False,
        help="Enable vacuity checking (default: off)")
    parser.add_argument("--no-vacuity", dest="vacuity", action="store_false",
        help="Skip vacuity checking")
    parser.add_argument("--mutation",    dest="mutation", action="store_true",  default=False,
        help="Enable mutation-based testing (default: off)")
    parser.add_argument("--no-mutation", dest="mutation", action="store_false",
        help="Skip mutation-based testing")

    args = parser.parse_args()

    jar   = str(safe_path(args.jar))
    model = str(safe_path(args.model))
    prop  = str(safe_path(args.property))

    skip_vacuity  = not args.vacuity
    skip_mutation = not args.mutation

    result = run_verification_gate(
        jar=jar,
        model=model,
        property_file=prop,
        rule_id=args.rule_id,
        output_dir=args.output_dir,
        rmc_timeout=args.rmc_timeout,
        vacuity_timeout=args.vacuity_timeout,
        max_mutants=args.max_mutants,
        mutation_timeout=args.mutation_timeout,
        seed=args.seed,
        skip_vacuity=skip_vacuity,
        skip_mutation=skip_mutation,
    )

    # Always write the canonical pipeline artifact — no LLM handover needed.
    artifact_path = step_artifact_path(args.rule_id, "step05_verification_gate", Path(args.base_dir))
    _write_atomic(artifact_path, result)

    if args.output_file:
        _write_atomic(Path(args.output_file), result)

    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps({"status": "ok", "passes_gate": result["passes_gate"], "artifact": str(artifact_path)}))


if __name__ == "__main__":
    main()
