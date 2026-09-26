#!/usr/bin/env python3
"""
Canonical output-path policy for the Legata→Rebeca pipeline.

All Step04–Step07 code MUST obtain paths exclusively through this module.
No step may construct output paths by string concatenation or suffix appending.

Directory contract
------------------
output/<rule_id>/<rule_id>.rebeca           ← promoted finals only
output/<rule_id>/<rule_id>.property         ← promoted finals only
output/reports/<rule_id>/summary.json
output/reports/<rule_id>/summary.md
output/reports/<rule_id>/verification.json
output/reports/<rule_id>/quality_gates.json
output/verification/<rule_id>/current/      ← single canonical verification view
output/work/<rule_id>/candidates/           ← scratch synthesis files (never promoted in-place)
output/work/<rule_id>/runs/<run_id>/attempt-<N>/
"""

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Rule-id validation
# ---------------------------------------------------------------------------

_RULE_ID_RE = re.compile(r'^[\w][\w\-]*$')


def _validate_rule_id(rule_id: str) -> None:
    """Raise ValueError if rule_id contains path-traversal or illegal characters."""
    if not rule_id or not _RULE_ID_RE.match(rule_id):
        raise ValueError(
            f"Invalid rule_id {rule_id!r}: must match [\\w][\\w\\-]* "
            "(alphanumeric, underscores, hyphens; no dots or slashes)"
        )


# ---------------------------------------------------------------------------
# Path groups (all as frozen dataclasses for immutability)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FinalPaths:
    """Promoted, canonical artifacts written into output/<rule_id>/."""
    rule_dir: Path
    model: Path
    property: Path


@dataclass(frozen=True)
class WorkPaths:
    """Scratch space for a specific pipeline run; never surfaces as a final artifact."""
    run_dir: Path
    candidates_dir: Path
    attempt_dir: Path


@dataclass(frozen=True)
class VerificationPaths:
    """Verification run directories; current/ is the single canonical view."""
    rule_verification_dir: Path
    current_dir: Path
    run_dir: Path


@dataclass(frozen=True)
class ReportPaths:
    """All report files for a rule, nested under output/reports/<rule_id>/."""
    report_dir: Path
    summary_json: Path
    summary_md: Path
    verification_json: Path
    quality_gates_json: Path


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def final_paths(rule_id: str, base_dir: Path = Path("output")) -> FinalPaths:
    """
    Return paths for the promoted final artifacts of *rule_id*.

    Args:
        rule_id: Identifier string for the rule (e.g. "COLREG-Rule22").
        base_dir: Repository-relative or absolute base directory (default: ``output``).

    Returns:
        :class:`FinalPaths` with ``rule_dir``, ``model``, ``property`` attributes.
    """
    _validate_rule_id(rule_id)
    rule_dir = Path(base_dir) / rule_id
    return FinalPaths(
        rule_dir=rule_dir,
        model=rule_dir / f"{rule_id}.rebeca",
        property=rule_dir / f"{rule_id}.property",
    )


def work_paths(
    rule_id: str,
    run_id: str,
    attempt: int = 1,
    base_dir: Path = Path("output"),
) -> WorkPaths:
    """
    Return scratch paths for a pipeline run.

    Args:
        rule_id: Rule identifier (validated).
        run_id:  Opaque run identifier (e.g. UUID or step label).  Must not
                 contain path separators.
        attempt: 1-based attempt counter within the run.
        base_dir: Base directory for the output tree.

    Returns:
        :class:`WorkPaths` with ``run_dir``, ``candidates_dir``, ``attempt_dir``.
    """
    _validate_rule_id(rule_id)
    if "/" in run_id or "\\" in run_id:
        raise ValueError(f"run_id must not contain path separators: {run_id!r}")
    if attempt < 1:
        raise ValueError(f"attempt must be >= 1, got {attempt}")

    work_root = Path(base_dir) / "work" / rule_id
    run_dir = work_root / "runs" / run_id
    return WorkPaths(
        run_dir=run_dir,
        candidates_dir=work_root / "candidates",
        attempt_dir=run_dir / f"attempt-{attempt}",
    )


def verification_paths(
    rule_id: str,
    run_id: str,
    base_dir: Path = Path("output"),
) -> VerificationPaths:
    """
    Return verification directories for *rule_id* / *run_id*.

    Step06 MUST write each attempt to ``run_dir`` and atomically publish the
    winner to ``current_dir`` after all attempts complete.

    Args:
        rule_id: Rule identifier (validated).
        run_id:  Run identifier corresponding to the current verification pass.
        base_dir: Base directory for the output tree.

    Returns:
        :class:`VerificationPaths` with ``rule_verification_dir``,
        ``current_dir``, ``run_dir``.
    """
    _validate_rule_id(rule_id)
    if "/" in run_id or "\\" in run_id:
        raise ValueError(f"run_id must not contain path separators: {run_id!r}")

    vdir = Path(base_dir) / "verification" / rule_id
    return VerificationPaths(
        rule_verification_dir=vdir,
        current_dir=vdir / "current",
        run_dir=vdir / run_id,
    )


def report_paths(rule_id: str, base_dir: Path = Path("output")) -> ReportPaths:
    """
    Return paths for all report files belonging to *rule_id*.

    Args:
        rule_id: Rule identifier (validated).
        base_dir: Base directory for the output tree.

    Returns:
        :class:`ReportPaths` with ``report_dir``, ``summary_json``,
        ``summary_md``, ``verification_json``, ``quality_gates_json``.
    """
    _validate_rule_id(rule_id)
    report_dir = Path(base_dir) / "reports" / rule_id
    return ReportPaths(
        report_dir=report_dir,
        summary_json=report_dir / "summary.json",
        summary_md=report_dir / "summary.md",
        verification_json=report_dir / "verification.json",
        quality_gates_json=report_dir / "quality_gates.json",
    )


# ---------------------------------------------------------------------------
# Candidate promotion
# ---------------------------------------------------------------------------

def promote_candidate(
    candidate_model: Path,
    candidate_property: Path,
    rule_id: str,
    base_dir: Path = Path("output"),
    overwrite: bool = True,
) -> FinalPaths:
    """
    Copy verified candidate files into the canonical final rule directory.

    Only verified candidates should be promoted; call this after Step06
    confirms the verification is non-vacuous and the mutation score is
    sufficient (>= 80).

    The source files are **not** removed; work/candidates/ is scratch space
    and may be cleaned up separately by :func:`cleanup_outputs`.

    Args:
        candidate_model:    Path to the candidate ``.rebeca`` model file.
        candidate_property: Path to the candidate ``.property`` file.
        rule_id:            Rule identifier (validated).
        base_dir:           Base output directory.
        overwrite:          If True (default), overwrite existing finals.
                            Set to False to protect existing verified artifacts.

    Returns:
        :class:`FinalPaths` pointing to the newly promoted files.

    Raises:
        FileNotFoundError: If either candidate source file does not exist.
        FileExistsError:   If *overwrite* is False and a final already exists.
    """
    _validate_rule_id(rule_id)

    if not candidate_model.exists():
        raise FileNotFoundError(f"Candidate model not found: {candidate_model}")
    if not candidate_property.exists():
        raise FileNotFoundError(f"Candidate property not found: {candidate_property}")

    fp = final_paths(rule_id, base_dir)
    fp.rule_dir.mkdir(parents=True, exist_ok=True)

    for src, dst in ((candidate_model, fp.model), (candidate_property, fp.property)):
        if dst.exists() and not overwrite:
            raise FileExistsError(
                f"Final artifact already exists (overwrite=False): {dst}"
            )
        shutil.copy2(src, dst)

    return fp


# ---------------------------------------------------------------------------
# Canonical vacuity sub-directories (used by vacuity_checker.py)
# ---------------------------------------------------------------------------

def vacuity_work_dirs(
    output_dir: str,
    rule_id: Optional[str] = None,
    run_id: str = "vacuity",
) -> tuple[str, str]:
    """
    Return canonical ``(secondary_output, baseline_output)`` paths for
    vacuity_checker.py, replacing the legacy ``<dir>_vacuity`` / ``<dir>_baseline``
    suffix pattern.

    If *rule_id* is provided, paths are placed under the work tree:
        ``output/work/<rule_id>/runs/<run_id>/vacuity/``
        ``output/work/<rule_id>/runs/<run_id>/baseline/``

    If *rule_id* is None (backward-compat), paths are placed as siblings
    inside *output_dir*:
        ``<output_dir>/vacuity/``
        ``<output_dir>/baseline/``

    Args:
        output_dir: The base output directory passed to ``check_vacuity()``.
        rule_id:    Optional rule identifier to place under the work tree.
        run_id:     Run identifier (default: ``"vacuity"``).

    Returns:
        ``(secondary_output_str, baseline_output_str)`` — both as ``str``
        for direct compatibility with :func:`run_rmc_detailed`.
    """
    base = Path(output_dir)
    if rule_id is not None:
        _validate_rule_id(rule_id)
        wp = work_paths(rule_id, run_id, base_dir=base)
        secondary = str(wp.run_dir / "vacuity")
        baseline = str(wp.run_dir / "baseline")
    else:
        secondary = str(base / "vacuity")
        baseline = str(base / "baseline")
    return secondary, baseline


def step_artifact_path(rule_id: str, step: str, base_dir: Path = Path("output")) -> Path:
    """Return canonical path for a step's durable artifact JSON.

    Convention: output/work/<rule_id>/<step>.json
    e.g. output/work/Rule-22/step02_abstraction.json
    """
    _validate_rule_id(rule_id)
    allowed = {
        "step02_abstraction", "step03_mapping", "step04_synthesis",
        "step05_verification_gate", "step06_packaging_manifest", "step07_reporting",
    }
    if step not in allowed:
        raise ValueError(f"Unknown step artifact name: {step!r}. Must be one of {sorted(allowed)}")
    return Path(base_dir) / "work" / rule_id / f"{step}.json"
