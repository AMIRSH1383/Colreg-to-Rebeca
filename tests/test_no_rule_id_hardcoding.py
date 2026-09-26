"""
Tests that output_policy path helpers are purely parametric —
no hardcoded rule IDs or fixed-depth assumptions.

These tests act as a contract that the path construction in output_policy.py
depends only on the *rule_id* and *base_dir* arguments, not on any
globals or project-specific constants.
"""

import string
from pathlib import Path

import pytest

from output_policy import (
    final_paths,
    report_paths,
    vacuity_work_dirs,
    verification_paths,
    work_paths,
)


# ---------------------------------------------------------------------------
# Parametric correctness — paths change with rule_id
# ---------------------------------------------------------------------------

SAMPLE_RULE_IDS = [
    "Rule1",
    "COLREG-Rule22",
    "MyRule_v2",
    "rule-with-hyphens",
    "a",
    "Rule_1_2_3",
]


@pytest.mark.parametrize("rule_id", SAMPLE_RULE_IDS)
def test_final_paths_contains_rule_id(tmp_path, rule_id):
    fp = final_paths(rule_id, base_dir=tmp_path)
    assert rule_id in str(fp.rule_dir)
    assert rule_id in fp.model.name
    assert rule_id in fp.property.name


@pytest.mark.parametrize("rule_id", SAMPLE_RULE_IDS)
def test_report_paths_contains_rule_id(tmp_path, rule_id):
    rp = report_paths(rule_id, base_dir=tmp_path)
    assert rule_id in str(rp.report_dir)


@pytest.mark.parametrize("rule_id", SAMPLE_RULE_IDS)
def test_work_paths_contains_rule_id(tmp_path, rule_id):
    wp = work_paths(rule_id, "run-1", base_dir=tmp_path)
    assert rule_id in str(wp.candidates_dir)
    assert rule_id in str(wp.run_dir)


@pytest.mark.parametrize("rule_id", SAMPLE_RULE_IDS)
def test_verification_paths_contains_rule_id(tmp_path, rule_id):
    vp = verification_paths(rule_id, "run-1", base_dir=tmp_path)
    assert rule_id in str(vp.rule_verification_dir)
    assert rule_id in str(vp.current_dir)


# ---------------------------------------------------------------------------
# base_dir isolation — two different base_dirs produce distinct paths
# ---------------------------------------------------------------------------

def test_different_base_dirs_produce_different_paths(tmp_path):
    base1 = tmp_path / "output-a"
    base2 = tmp_path / "output-b"
    fp1 = final_paths("Rule22", base_dir=base1)
    fp2 = final_paths("Rule22", base_dir=base2)
    assert fp1.rule_dir != fp2.rule_dir
    assert fp1.model != fp2.model


def test_base_dir_appears_in_all_paths(tmp_path):
    base = tmp_path / "my-custom-output"
    fp = final_paths("Rule22", base_dir=base)
    wp = work_paths("Rule22", "run-1", base_dir=base)
    rp = report_paths("Rule22", base_dir=base)
    vp = verification_paths("Rule22", "run-1", base_dir=base)

    assert str(base) in str(fp.rule_dir)
    assert str(base) in str(wp.candidates_dir)
    assert str(base) in str(rp.report_dir)
    assert str(base) in str(vp.current_dir)


# ---------------------------------------------------------------------------
# Invalid rule_id rejection (path-traversal guard)
# ---------------------------------------------------------------------------

INVALID_RULE_IDS = [
    "../traversal",
    "rule/with/slash",
    "rule\\backslash",
    "",
    "rule id with space",
    ".hidden",
    "rule.with.dots",
]


@pytest.mark.parametrize("bad_id", INVALID_RULE_IDS)
def test_final_paths_rejects_invalid_rule_id(tmp_path, bad_id):
    with pytest.raises((ValueError, SystemExit)):
        final_paths(bad_id, base_dir=tmp_path)


@pytest.mark.parametrize("bad_id", INVALID_RULE_IDS)
def test_report_paths_rejects_invalid_rule_id(tmp_path, bad_id):
    with pytest.raises((ValueError, SystemExit)):
        report_paths(bad_id, base_dir=tmp_path)


@pytest.mark.parametrize("bad_id", INVALID_RULE_IDS)
def test_work_paths_rejects_invalid_rule_id(tmp_path, bad_id):
    with pytest.raises((ValueError, SystemExit)):
        work_paths(bad_id, "run-1", base_dir=tmp_path)


# ---------------------------------------------------------------------------
# Immutability — returned dataclasses are frozen
# ---------------------------------------------------------------------------

def test_final_paths_is_frozen(tmp_path):
    fp = final_paths("Rule22", base_dir=tmp_path)
    with pytest.raises((AttributeError, TypeError)):
        fp.model = Path("/evil")  # type: ignore[misc]


def test_work_paths_is_frozen(tmp_path):
    wp = work_paths("Rule22", "run-1", base_dir=tmp_path)
    with pytest.raises((AttributeError, TypeError)):
        wp.candidates_dir = Path("/evil")  # type: ignore[misc]


def test_report_paths_is_frozen(tmp_path):
    rp = report_paths("Rule22", base_dir=tmp_path)
    with pytest.raises((AttributeError, TypeError)):
        rp.summary_json = Path("/evil")  # type: ignore[misc]


def test_verification_paths_is_frozen(tmp_path):
    vp = verification_paths("Rule22", "run-1", base_dir=tmp_path)
    with pytest.raises((AttributeError, TypeError)):
        vp.current_dir = Path("/evil")  # type: ignore[misc]
