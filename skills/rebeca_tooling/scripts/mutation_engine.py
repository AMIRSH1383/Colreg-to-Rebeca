#!/usr/bin/env python3
"""
Mutation Engine for semantic validation of Legata→Rebeca transformations.

Applies controlled mutations to .rebeca and .property files to verify semantic
strength. A well-formed transformation should produce different RMC outcomes
(kill the mutant) when mutations are applied.

Mutation strategies:
  .rebeca:    transition_bypass, predicate_flip, assignment_mutation
  .property:  comparison_value_mutation, boolean_predicate_negation,
              assertion_negation, assertion_predicate_inversion,
              logical_swap, variable_swap

Design: all mutate_* methods return new content strings — never mutate in place.
Callers write mutants to disk and invoke RMC; this module only generates text.

Exit codes (CLI):
  0: Mutants generated successfully
  1: Invalid inputs or file not found
"""

import argparse
import datetime
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from run_rmc import run_rmc_detailed
from utils import safe_path


@dataclass
class Mutation:
    """Represents a single applied mutation with full before/after content."""
    mutation_id: str          # e.g. "Rule-22_m_tb_01"
    strategy: str             # e.g. "transition_bypass"
    artifact: str             # "model" or "property"
    original_content: str     # unmodified file text
    mutated_content: str      # mutated file text
    description: str          # human-readable description of the change


class MutationEngine:
    """
    Generates mutated variants of .rebeca and .property files.

    All methods are pure: they take content strings and return Mutation
    objects. No file I/O is performed here.
    """

    # ------------------------------------------------------------------ #
    #  .rebeca model mutations                                             #
    # ------------------------------------------------------------------ #

    def transition_bypass(self, content: str, rule_id: str) -> List[Mutation]:
        """
        Bypass msgsrv bodies by commenting out assignment statements.
        One mutant per msgsrv that contains at least one assignment.
        """
        mutations: List[Mutation] = []
        pattern = re.compile(
            r'(msgsrv\s+\w+\s*\([^)]*\)\s*\{)([^}]+)(\})',
            re.DOTALL,
        )
        match_index = 0
        for m in pattern.finditer(content):
            body = m.group(2)
            if '=' not in body:
                continue
            mutated_body = re.sub(r'([^\n]*=[^\n]*\n)', r'/* \1*/\n', body)
            if mutated_body == body:
                continue
            mutated_content = content[: m.start(2)] + mutated_body + content[m.end(2) :]
            match_index += 1
            mutations.append(Mutation(
                mutation_id=f"{rule_id}_m_tb_{match_index:02d}",
                strategy="transition_bypass",
                artifact="model",
                original_content=content,
                mutated_content=mutated_content,
                description=f"Bypassed assignments in msgsrv block #{match_index}",
            ))
        return mutations

    def predicate_flip(self, content: str, rule_id: str) -> List[Mutation]:
        """
        Negate if-conditions: `if (cond)` → `if (!(cond))`.
        One mutant per if-statement found. Skips already-negated conditions.
        """
        mutations: List[Mutation] = []
        pattern = re.compile(r'(if\s*\()([^)]+)(\))', re.MULTILINE)
        match_index = 0
        for m in pattern.finditer(content):
            inner = m.group(2).strip()
            if inner.startswith('!'):
                continue
            mutated_condition = f"!({inner})"
            mutated_content = (
                content[: m.start(2)] + mutated_condition + content[m.end(2) :]
            )
            match_index += 1
            mutations.append(Mutation(
                mutation_id=f"{rule_id}_m_pf_{match_index:02d}",
                strategy="predicate_flip",
                artifact="model",
                original_content=content,
                mutated_content=mutated_content,
                description=f"Negated if-condition #{match_index}: '{inner}' → '!({inner})'",
            ))
        return mutations

    def assignment_mutation(self, content: str, rule_id: str) -> List[Mutation]:
        """
        Increment numeric literals in assignment RHS: `v = v + 1;` → `v = v + 2;`.
        One mutant per numeric literal found in an assignment statement.
        """
        mutations: List[Mutation] = []
        # Match assignment statements with a numeric literal on the RHS
        pattern = re.compile(r'(\w+\s*=\s*[^;]*?)(\b\d+\b)([^;]*;)', re.MULTILINE)
        match_index = 0
        for m in pattern.finditer(content):
            original_num = int(m.group(2))
            mutated_num = original_num + 1
            mutated_content = (
                content[: m.start(2)] + str(mutated_num) + content[m.end(2) :]
            )
            match_index += 1
            mutations.append(Mutation(
                mutation_id=f"{rule_id}_m_am_{match_index:02d}",
                strategy="assignment_mutation",
                artifact="model",
                original_content=content,
                mutated_content=mutated_content,
                description=f"Incremented numeric literal in assignment: {original_num} → {mutated_num}",
            ))
        return mutations

    # ------------------------------------------------------------------ #
    #  .property specification mutations                                   #
    # ------------------------------------------------------------------ #

    def comparison_value_mutation(self, content: str, rule_id: str) -> List[Mutation]:
        """
        Increment numeric literals inside define block comparisons.
        `isOverLimit = (s1.length > 50)` → `isOverLimit = (s1.length > 51)`
        """
        mutations: List[Mutation] = []
        block = self._extract_define_block(content)
        if block is None:
            return mutations
        start, end, block_text = block
        pattern = re.compile(r'([><=!]=?\s*)(\d+)', re.MULTILINE)
        match_index = 0
        for m in pattern.finditer(block_text):
            original_num = int(m.group(2))
            mutated_num = original_num + 1
            mutated_block = (
                block_text[: m.start(2)] + str(mutated_num) + block_text[m.end(2) :]
            )
            mutated_content = content[:start] + mutated_block + content[end:]
            match_index += 1
            mutations.append(Mutation(
                mutation_id=f"{rule_id}_m_cvm_{match_index:02d}",
                strategy="comparison_value_mutation",
                artifact="property",
                original_content=content,
                mutated_content=mutated_content,
                description=f"Incremented comparison value: {original_num} → {mutated_num}",
            ))
        return mutations

    def boolean_predicate_negation(self, content: str, rule_id: str) -> List[Mutation]:
        """
        Negate define-block definitions.
        `isSafe = (s1.speed < 10)` → `isSafe = !(s1.speed < 10)`
        """
        mutations: List[Mutation] = []
        block = self._extract_define_block(content)
        if block is None:
            return mutations
        start, end, block_text = block
        # Match: varName = (expr);
        pattern = re.compile(r'(\w+\s*=\s*)(\([^)]+\))\s*;', re.MULTILINE)
        match_index = 0
        for m in pattern.finditer(block_text):
            original_expr = m.group(2)
            # Skip already-negated definitions
            preceding_char = block_text[m.start(2) - 1 : m.start(2)].strip()
            if preceding_char == '!':
                continue
            mutated_block = (
                block_text[: m.start(2)] + f"!{original_expr}" + block_text[m.end(2) :]
            )
            mutated_content = content[:start] + mutated_block + content[end:]
            match_index += 1
            mutations.append(Mutation(
                mutation_id=f"{rule_id}_m_bpn_{match_index:02d}",
                strategy="boolean_predicate_negation",
                artifact="property",
                original_content=content,
                mutated_content=mutated_content,
                description=f"Negated define expression #{match_index}: '!{original_expr}'",
            ))
        return mutations

    def assertion_negation(self, content: str, rule_id: str) -> List[Mutation]:
        """
        Negate entire assertions: `RuleName: A;` → `RuleName: !A;`.
        One mutant per assertion entry. Toggles existing leading negation.
        """
        mutations: List[Mutation] = []
        block = self._extract_assertion_block(content)
        if block is None:
            return mutations
        start, end, block_text = block
        # Match: AssertionName: [optional !]expression;
        pattern = re.compile(r'(\w+\s*:\s*)(!?)(.+?)(;)', re.DOTALL)
        match_index = 0
        for m in pattern.finditer(block_text):
            existing_negation = m.group(2)
            expr = m.group(3).strip()
            # Toggle: add ! if absent, remove if present
            mutated_expr = expr if existing_negation == '!' else f"!{expr}"
            mutated_block = (
                block_text[: m.start(2)]
                + mutated_expr
                + block_text[m.end(3) :]
            )
            mutated_content = content[:start] + mutated_block + content[end:]
            match_index += 1
            mutations.append(Mutation(
                mutation_id=f"{rule_id}_m_an_{match_index:02d}",
                strategy="assertion_negation",
                artifact="property",
                original_content=content,
                mutated_content=mutated_content,
                description=f"Toggled negation on assertion #{match_index}",
            ))
        return mutations

    def assertion_predicate_inversion(self, content: str, rule_id: str) -> List[Mutation]:
        """
        Negate specific predicates within an assertion while keeping the define block.
        `A && B` → `!A && B` (one mutant per predicate term in the assertion).
        """
        mutations: List[Mutation] = []
        block = self._extract_assertion_block(content)
        if block is None:
            return mutations
        start, end, block_text = block
        # Find individual predicate references (word tokens that are not operators)
        # Matches bare variable names used in assertions (not actor.var — those are in define)
        pattern = re.compile(r'\b([A-Za-z_]\w*)\b(?!\s*[:(])')
        match_index = 0
        for m in pattern.finditer(block_text):
            term = m.group(1)
            # Skip keywords
            if term in ('Assertion', 'LTL', 'define', 'property', 'G', 'F', 'X', 'U'):
                continue
            mutated_block = (
                block_text[: m.start()] + f"!{term}" + block_text[m.end() :]
            )
            mutated_content = content[:start] + mutated_block + content[end:]
            match_index += 1
            mutations.append(Mutation(
                mutation_id=f"{rule_id}_m_api_{match_index:02d}",
                strategy="assertion_predicate_inversion",
                artifact="property",
                original_content=content,
                mutated_content=mutated_content,
                description=f"Negated predicate term '{term}' in assertion",
            ))
        return mutations

    def logical_swap(self, content: str, rule_id: str) -> List[Mutation]:
        """
        Swap && with || (and vice versa) in the assertion block.
        One mutant per operator occurrence.
        """
        mutations: List[Mutation] = []
        block = self._extract_assertion_block(content)
        if block is None:
            return mutations
        start, end, block_text = block
        pattern = re.compile(r'(&&|\|\|)')
        match_index = 0
        for m in pattern.finditer(block_text):
            original_op = m.group(1)
            swapped_op = '||' if original_op == '&&' else '&&'
            mutated_block = (
                block_text[: m.start()] + swapped_op + block_text[m.end() :]
            )
            mutated_content = content[:start] + mutated_block + content[end:]
            match_index += 1
            mutations.append(Mutation(
                mutation_id=f"{rule_id}_m_ls_{match_index:02d}",
                strategy="logical_swap",
                artifact="property",
                original_content=content,
                mutated_content=mutated_content,
                description=f"Swapped '{original_op}' → '{swapped_op}' in assertion",
            ))
        return mutations

    def variable_swap(self, content: str, rule_id: str) -> List[Mutation]:
        """
        Replace a state variable reference with another from the same actor.
        Finds all `actorName.varName` patterns; swaps among same-actor variables.
        One mutant per (actor, var) pair that has at least one other candidate.
        """
        mutations: List[Mutation] = []
        block = self._extract_assertion_block(content)
        # Fall back to full content if no Assertion block found
        start, end, block_text = block if block is not None else (0, len(content), content)

        ref_pattern = re.compile(r'\b(\w+)\.(\w+)\b')
        refs: Dict[str, List[str]] = {}
        for m in ref_pattern.finditer(block_text):
            actor, var = m.group(1), m.group(2)
            if var not in refs.setdefault(actor, []):
                refs[actor].append(var)

        match_index = 0
        for actor, variables in refs.items():
            if len(variables) < 2:
                continue
            for i, original_var in enumerate(variables):
                swap_var = variables[(i + 1) % len(variables)]
                # Use regex with word boundaries to avoid partial-name replacement
                mutated_block = re.sub(
                    r'\b' + re.escape(actor) + r'\.' + re.escape(original_var) + r'\b',
                    f"{actor}.{swap_var}",
                    block_text,
                    count=1,
                )
                if mutated_block == block_text:
                    continue
                mutated_content = content[:start] + mutated_block + content[end:]
                match_index += 1
                mutations.append(Mutation(
                    mutation_id=f"{rule_id}_m_vs_{match_index:02d}",
                    strategy="variable_swap",
                    artifact="property",
                    original_content=content,
                    mutated_content=mutated_content,
                    description=f"Swapped '{actor}.{original_var}' → '{actor}.{swap_var}'",
                ))
        return mutations

    # ------------------------------------------------------------------ #
    #  Batch orchestration                                                 #
    # ------------------------------------------------------------------ #

    def mutate_model(self, content: str, rule_id: str) -> List[Mutation]:
        """Apply all .rebeca mutation strategies and return combined list."""
        return (
            self.transition_bypass(content, rule_id)
            + self.predicate_flip(content, rule_id)
            + self.assignment_mutation(content, rule_id)
        )

    def mutate_property(self, content: str, rule_id: str) -> List[Mutation]:
        """Apply all .property mutation strategies and return combined list."""
        return (
            self.comparison_value_mutation(content, rule_id)
            + self.boolean_predicate_negation(content, rule_id)
            + self.assertion_negation(content, rule_id)
            + self.assertion_predicate_inversion(content, rule_id)
            + self.logical_swap(content, rule_id)
            + self.variable_swap(content, rule_id)
        )

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _extract_define_block(self, content: str) -> Optional[Tuple[int, int, str]]:
        """Return (start, end, text) of the interior of define { ... }, or None."""
        m = re.search(r'\bdefine\s*\{([^}]*)\}', content, re.DOTALL)
        return (m.start(1), m.end(1), m.group(1)) if m else None

    def _extract_assertion_block(self, content: str) -> Optional[Tuple[int, int, str]]:
        """Return (start, end, text) of the interior of Assertion { ... }, or None."""
        m = re.search(r'\bAssertion\s*\{([^}]*)\}', content, re.DOTALL)
        return (m.start(1), m.end(1), m.group(1)) if m else None


# ------------------------------------------------------------------ #
#  CLI                                                                 #
# ------------------------------------------------------------------ #

_MODEL_STRATEGIES = ("transition_bypass", "predicate_flip", "assignment_mutation")
_PROPERTY_STRATEGIES = (
    "comparison_value_mutation", "boolean_predicate_negation",
    "assertion_negation", "assertion_predicate_inversion",
    "logical_swap", "variable_swap",
)


def _is_semantic_outcome(value: Optional[str]) -> bool:
    return value in ("satisfied", "cex")


def run_mutants(
    mutations: List["Mutation"],
    jar: str,
    model_path: Optional[Path],
    property_path: Optional[Path],
    timeout_seconds: int = 60,
    max_mutants: int = 50,
    total_timeout: int = 600,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Execute each mutant and compare semantic outcomes against baseline.

        Baseline and mutant outcomes are taken from a combined signal:
            1) RMC process phase (run_rmc_detailed)
            2) model.out execution outcome

    A mutant is **killed** iff semantic outcome flips between
    ``satisfied`` and ``cex`` relative to baseline. If the mutant cannot
    produce a comparable semantic outcome, it is counted as ``error``.

    Args:
        mutations:        List of Mutation objects to execute.
        jar:              Path to rmc.jar.
        model_path:       Canonical (unmodified) .rebeca file path.
        property_path:    Canonical (unmodified) .property file path.
        timeout_seconds:  Per-mutant RMC timeout.
        max_mutants:      Cap on number of mutants to execute after sampling.
        total_timeout:    Wall-clock budget (seconds) for all mutant runs.
        seed:             Random seed for reproducible sampling.

    Returns:
        {
          "total_generated": int,
          "total_run":       int,
          "sampled":         bool,
          "sample_seed":     int,
          "budget_exceeded": bool,
          "elapsed_seconds": float,
          "baseline_outcome": str|None,
          "killed":          int,
          "survived":        int,
          "errors":          int,
          "mutation_score":  float,
          "mutant_results":  [{"mutation_id": str,
                                 "outcome": "killed"|"survived"|"error"|"budget_exceeded",
                                 "exit_code": int|None}]
        }
    """
    jar_path = safe_path(jar)
    results: List[Dict[str, Any]] = []
    killed = 0
    survived = 0
    errors = 0
    total_generated = len(mutations)
    sampled = False

    selected_mutations = list(mutations)
    if max_mutants < 0:
        max_mutants = 0
    if len(selected_mutations) > max_mutants:
        sampled = True
        selected_mutations = random.Random(seed).sample(selected_mutations, max_mutants)
        print(
            f"[mutation_engine] Sampling {max_mutants} of {total_generated} mutants (--max-mutants={max_mutants})",
            file=sys.stderr,
        )

    baseline_outcome: Optional[str] = None
    baseline_details: Optional[Dict[str, Any]] = None
    if model_path is not None and property_path is not None:
        baseline_dir = Path.home() / f".mutation_baseline_{int(time.time() * 1000)}"
        baseline_details = run_rmc_detailed(
            jar=str(jar_path),
            model=str(model_path),
            property_file=str(property_path),
            output_dir=str(baseline_dir),
            timeout_seconds=timeout_seconds,
            run_model_outcome=True,
            model_out_timeout_seconds=timeout_seconds,
        )
        outcome = baseline_details.get("verification_outcome")
        if isinstance(outcome, str) and _is_semantic_outcome(outcome):
            baseline_outcome = outcome

    start_time = time.monotonic()
    budget_exceeded = False
    elapsed_seconds = 0.0

    for idx, mut in enumerate(selected_mutations):
        elapsed_seconds = time.monotonic() - start_time
        if elapsed_seconds >= total_timeout:
            budget_exceeded = True
            print(
                f"[mutation_engine] Total timeout reached after {elapsed_seconds:.0f}s",
                file=sys.stderr,
            )
            for pending in selected_mutations[idx:]:
                results.append(
                    {
                        "mutation_id": pending.mutation_id,
                        "outcome": "budget_exceeded",
                        "exit_code": None,
                    }
                )
            break

        # Write the mutant to a temp file in the same directory as the original
        # so safe_path() constraints are satisfied (within home).
        if mut.artifact == "model" and model_path is not None:
            suffix = ".rebeca"
        elif mut.artifact == "property" and property_path is not None:
            suffix = ".property"
        else:
            results.append({"mutation_id": mut.mutation_id, "outcome": "error",
                            "exit_code": -1, "reason": "no matching original path"})
            errors += 1
            continue

        tmp_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=suffix,
                delete=False,
                encoding="utf-8",
                dir=Path.home(),
            ) as tmp:
                tmp.write(mut.mutated_content)
                tmp_path = Path(tmp.name)

            # Build RMC command
            if mut.artifact == "model":
                rmc_model = str(tmp_path)
                rmc_prop = str(property_path) if property_path else None
            else:
                rmc_model = str(model_path) if model_path else None
                rmc_prop = str(tmp_path)

            if rmc_model is None or rmc_prop is None:
                results.append({"mutation_id": mut.mutation_id, "outcome": "error",
                                "exit_code": -1, "reason": "missing counterpart file"})
                errors += 1
                continue

            with tempfile.TemporaryDirectory(dir=Path.home()) as tmp_out:
                detailed = run_rmc_detailed(
                    jar=str(jar_path),
                    model=rmc_model,
                    property_file=rmc_prop,
                    output_dir=tmp_out,
                    timeout_seconds=timeout_seconds,
                    run_model_outcome=True,
                    model_out_timeout_seconds=timeout_seconds,
                )
                exit_code = detailed.get("rmc_exit_code")
                mutant_outcome = detailed.get("verification_outcome")
        except subprocess.TimeoutExpired:
            exit_code = 3  # treat timeout as survived (indeterminate)
            mutant_outcome = "timeout"
        except Exception as exc:
            results.append({"mutation_id": mut.mutation_id, "outcome": "error",
                            "exit_code": -1, "reason": str(exc)})
            errors += 1
            continue
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

        if baseline_outcome is None:
            outcome = "error"
            errors += 1
            results.append(
                {
                    "mutation_id": mut.mutation_id,
                    "outcome": outcome,
                    "exit_code": exit_code,
                    "baseline_outcome": baseline_outcome,
                    "mutant_outcome": mutant_outcome,
                    "reason": "baseline semantic outcome unavailable",
                }
            )
            continue

        if not _is_semantic_outcome(mutant_outcome):
            outcome = "error"
            errors += 1
            results.append(
                {
                    "mutation_id": mut.mutation_id,
                    "outcome": outcome,
                    "exit_code": exit_code,
                    "baseline_outcome": baseline_outcome,
                    "mutant_outcome": mutant_outcome,
                    "reason": "mutant semantic outcome unavailable",
                }
            )
            continue

        # Kill criterion: semantic result flips satisfied <-> cex.
        outcome = "killed" if mutant_outcome != baseline_outcome else "survived"
        if outcome == "killed":
            killed += 1
        else:
            survived += 1
        results.append(
            {
                "mutation_id": mut.mutation_id,
                "outcome": outcome,
                "exit_code": exit_code,
                "baseline_outcome": baseline_outcome,
                "mutant_outcome": mutant_outcome,
            }
        )

    elapsed_seconds = time.monotonic() - start_time
    total_run = killed + survived + errors
    mutation_score = round(killed / total_run * 100, 2) if total_run > 0 else 0.0

    return {
        "total_generated": total_generated,
        "total_run": total_run,
        "sampled": sampled,
        "sample_seed": seed,
        "budget_exceeded": budget_exceeded,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "baseline_outcome": baseline_outcome,
        "baseline_details": baseline_details,
        "killed": killed,
        "survived": survived,
        "errors": errors,
        "mutation_score": mutation_score,
        "mutant_results": results,
        # Backward-compatible alias
        "total": total_run,
    }


def write_mutation_artifact(output_file: Path, payload: Dict[str, Any]) -> None:
    """
    Atomically write *payload* as UTF-8 JSON to *output_file*.

    Uses a sibling temp file + os.replace() so callers never observe a
    partial or empty file even if the process is interrupted mid-write.

    Raises:
        ValueError: if the resulting JSON would be empty or the payload
                    missing required keys.
        OSError:    on filesystem errors (propagated to caller).
    """
    required_key_sets = ({"rule_id"}, {"mutants", "total_mutants", "kill_stats"})
    has_rule_id = "rule_id" in payload
    has_content_key = bool({"mutants", "total_mutants", "kill_stats"} & payload.keys())
    if not has_rule_id or not has_content_key:
        missing = []
        if not has_rule_id:
            missing.append("rule_id")
        if not has_content_key:
            missing.append("one of mutants/total_mutants/kill_stats")
        raise ValueError(
            f"Mutation artifact payload missing required keys: {', '.join(missing)}"
        )

    serialised = json.dumps(payload, indent=2, ensure_ascii=False)
    if not serialised.strip():
        raise ValueError("Serialised mutation artifact is empty")

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Write to a sibling temp file, then rename atomically.
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
        # Best-effort cleanup of the temp file on error.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    # Post-condition: file must be non-empty and parseable.
    size = output_file.stat().st_size
    if size == 0:
        raise OSError(f"Artifact written to {output_file} is 0 bytes after rename")


def write_mutation_error_artifact(
    output_file: Path,
    rule_id: str,
    *,
    command: Optional[List[str]] = None,
    return_code: Optional[int] = None,
    stdout_preview: str = "",
    stderr_preview: str = "",
    exception_msg: str = "",
) -> Path:
    """
    Write a structured error artifact as ``<output_file>.error.json``.

    This is always written on failure so that downstream steps receive an
    explicit error signal rather than a missing or empty artifact.

    Returns the path of the error file written.
    """
    error_path = output_file.with_suffix(".error.json")
    error_path.parent.mkdir(parents=True, exist_ok=True)

    payload: Dict[str, Any] = {
        "status": "error",
        "rule_id": rule_id,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "command": command or [],
        "return_code": return_code,
        "stdout_preview": stdout_preview[:2000],
        "stderr_preview": stderr_preview[:2000],
        "exception": exception_msg,
    }
    serialised = json.dumps(payload, indent=2, ensure_ascii=False)
    error_path.write_text(serialised, encoding="utf-8")
    return error_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate mutation variants of .rebeca/.property files for semantic validation"
    )
    parser.add_argument("--rule-id", required=True, help="Rule identifier (e.g., Rule-22)")
    parser.add_argument("--model", default=None, help="Path to .rebeca model file")
    parser.add_argument("--property", default=None, help="Path to .property file")
    parser.add_argument(
        "--strategy",
        default="all",
        choices=("all",) + _MODEL_STRATEGIES + _PROPERTY_STRATEGIES,
        help="Mutation strategy to apply (default: all)",
    )
    parser.add_argument(
        "--output-json", action="store_true", help="Output results as JSON to stdout"
    )
    parser.add_argument(
        "--output-file",
        default=None,
        metavar="PATH",
        help=(
            "Write mutation artifact as JSON to PATH atomically (temp + rename). "
            "On failure, writes PATH.error.json and exits non-zero. "
            "Preferred over shell redirection of --output-json."
        ),
    )
    # ── optional kill-run mode ──────────────────────────────────────────────
    run_group = parser.add_argument_group(
        "kill-run mode",
        "Pass all three flags to execute mutants with RMC and report kill score.",
    )
    run_group.add_argument("--run-with-jar", default=None,
                           help="Path to rmc.jar for executing mutants")
    run_group.add_argument("--run-with-model", default=None,
                           help="Path to canonical .rebeca model (used when mutating property)")
    run_group.add_argument("--run-with-property", default=None,
                           help="Path to canonical .property file (used when mutating model)")
    run_group.add_argument("--run-timeout", type=int, default=60,
                           help="Per-mutant RMC timeout in seconds (default: 60)")
    run_group.add_argument("--max-mutants", type=int, default=50,
                           help="Cap on number of mutants to execute (default: 50)")
    run_group.add_argument("--total-timeout", type=int, default=600,
                           help="Total wall-clock budget for kill-run in seconds (default: 600)")
    run_group.add_argument("--seed", type=int, default=42,
                           help="Random seed for reproducible mutant sampling (default: 42)")
    args = parser.parse_args()

    if args.model is None and args.property is None:
        print("Error: at least one of --model or --property is required", file=sys.stderr)
        sys.exit(1)

    engine = MutationEngine()
    mutations: List[Mutation] = []

    if args.model:
        model_path = safe_path(args.model)
        if not model_path.exists():
            print(f"Error: model file not found: {args.model}", file=sys.stderr)
            sys.exit(1)
        model_content = model_path.read_text(encoding="utf-8")
        for strategy in _MODEL_STRATEGIES:
            if args.strategy in ("all", strategy):
                mutations += getattr(engine, strategy)(model_content, args.rule_id)

    if args.property:
        prop_path = safe_path(args.property)
        if not prop_path.exists():
            print(f"Error: property file not found: {args.property}", file=sys.stderr)
            sys.exit(1)
        prop_content = prop_path.read_text(encoding="utf-8")
        for strategy in _PROPERTY_STRATEGIES:
            if args.strategy in ("all", strategy):
                mutations += getattr(engine, strategy)(prop_content, args.rule_id)

    mutant_summary = [
        {k: v for k, v in asdict(m).items()
         if k not in ("original_content", "mutated_content")}
        for m in mutations
    ]

    # ── kill-run mode ───────────────────────────────────────────────────────
    kill_stats: Optional[Dict[str, Any]] = None
    is_kill_run_mode = bool(args.run_with_jar)
    if is_kill_run_mode:
        if not mutations:
            print("Warning: no mutants generated — skipping kill-run", file=sys.stderr)
        else:
            kill_stats = run_mutants(
                mutations=mutations,
                jar=args.run_with_jar,
                model_path=safe_path(args.run_with_model) if args.run_with_model else None,
                property_path=(
                    safe_path(args.run_with_property) if args.run_with_property else None
                ),
                timeout_seconds=args.run_timeout,
                max_mutants=args.max_mutants,
                total_timeout=args.total_timeout,
                seed=args.seed,
            )

    mode = "kill_run" if is_kill_run_mode else "catalog_only"

    if kill_stats is None and not is_kill_run_mode:
        print(
            "[mutation_engine] Catalog-only mode: "
            f"{len(mutations)} mutants generated.\n"
            "To score mutants, add: --run-with-jar <jar> --run-with-model <model>\n"
            "                          --run-with-property <property>",
            file=sys.stderr,
        )

    output: Dict[str, Any] = {
        "mode": mode,
        "rule_id": args.rule_id,
        "total_mutants": len(mutations),
        "mutants": mutant_summary,
    }
    if kill_stats is not None:
        output["kill_stats"] = kill_stats

    # ── --output-file: atomic write with error artifact on failure ──────────
    if args.output_file:
        output_path = safe_path(args.output_file)
        try:
            write_mutation_artifact(output_path, output)
        except Exception as exc:
            error_path = write_mutation_error_artifact(
                output_path,
                rule_id=args.rule_id,
                exception_msg=str(exc),
            )
            print(
                f"[mutation_engine] ERROR: failed to write artifact to {output_path}: {exc}\n"
                f"  Diagnostics written to: {error_path}",
                file=sys.stderr,
            )
            sys.exit(1)

    # ── --output-json: stdout JSON (backward-compatible) ───────────────────
    if args.output_json:
        print(json.dumps(output, indent=2))
    elif not args.output_file:
        # Human-readable summary when neither flag is given
        print(f"Rule:            {args.rule_id}")
        print(f"Total mutants:   {len(mutations)}")
        for m in mutations:
            print(f"  [{m.mutation_id}] {m.strategy} ({m.artifact}): {m.description}")
        if kill_stats is not None:
            print()
            print(f"Kill-run results:")
            print(f"  Killed:         {kill_stats['killed']}/{kill_stats['total_run']}")
            print(f"  Survived:       {kill_stats['survived']}")
            print(f"  Errors:         {kill_stats['errors']}")
            print(f"  Mutation score: {kill_stats['mutation_score']:.1f}%")
        if kill_stats is None:
            print("Tip: re-run with --run-with-jar/model/property to score mutant kill rate.")

    sys.exit(0)


if __name__ == "__main__":
    main()
