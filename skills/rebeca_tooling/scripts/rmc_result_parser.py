#!/usr/bin/env python3
"""Parse RMC/model.out exported result artifacts into normalized outcomes."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict

from utils import safe_path

_NEGATIVE_PATTERNS = (
    "counterexample",
    "not satisfied",
    "property violated",
    "violated",
    "fail",
    "false",
    "unsafe",
)

_POSITIVE_PATTERNS = (
    "property is satisfied",
    "satisfied",
    "verified",
    "pass",
    "true",
    "safe",
)


def _local_name(tag: Any) -> str:
    """Return lowercase local XML tag name (namespace-agnostic)."""
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        tag = tag.split("}", 1)[1]
    return tag.strip().lower()


def _trace_has_content(trace_elem: ET.Element) -> bool:
    """Determine whether a counter-example trace element is semantically non-empty."""
    if (trace_elem.text or "").strip():
        return True
    if trace_elem.attrib:
        return True
    if len(trace_elem) > 0:
        return True
    for child in trace_elem.iter():
        if child is trace_elem:
            continue
        if (child.text or "").strip() or child.attrib or len(child) > 0:
            return True
    return False


def _normalise_status(text: str) -> str:
    """Map free-text verdict content to semantic outcome labels."""
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    if not normalized:
        return "unknown"

    if any(pattern in normalized for pattern in _NEGATIVE_PATTERNS):
        return "cex"
    if any(pattern in normalized for pattern in _POSITIVE_PATTERNS):
        return "satisfied"
    return "unknown"


def _extract_xml_signal(root: ET.Element) -> str:
    """Extract semantic signal from XML tags/attributes/text."""
    trace_tags = {
        "counter-example-trace",
        "counterexampletrace",
        "counter_example_trace",
    }
    status_tags = {"result", "verification", "status", "verdict", "outcome", "property"}

    trace_seen = False
    candidates = []

    for elem in root.iter():
        local_tag = _local_name(elem.tag)
        if local_tag in trace_tags:
            trace_seen = True
            if _trace_has_content(elem):
                return "cex"

        for key, value in elem.attrib.items():
            key_lower = str(key).strip().lower()
            value_lower = str(value).strip().lower()

            if key_lower in {"status", "result", "verdict", "outcome"}:
                candidates.append(value_lower)
            elif key_lower in {"satisfied", "is_satisfied", "holds"}:
                if value_lower in {"true", "1", "yes"}:
                    candidates.append("satisfied")
                elif value_lower in {"false", "0", "no"}:
                    candidates.append("cex")

        if local_tag in status_tags and elem.text and elem.text.strip():
            candidates.append(elem.text.strip())

    normalized_candidates = {
        candidate.strip().lower() for candidate in candidates if candidate and candidate.strip()
    }
    if "cex" in normalized_candidates:
        return "cex"
    if "satisfied" in normalized_candidates:
        return "satisfied"

    status = _normalise_status("\n".join(candidates))
    if status in {"satisfied", "cex"}:
        return status

    if trace_seen:
        return "unknown"

    return "unknown"


def parse_rmc_result_file(result_path: str) -> Dict[str, Any]:
    """Parse model.out/RMC exported result artifact and normalize outcome."""
    try:
        path = safe_path(result_path)
    except SystemExit:
        return {
            "path": result_path,
            "exists": False,
            "parsed": False,
            "format": "unknown",
            "outcome": "unknown",
            "error": f"Invalid result path: {result_path}",
        }

    result: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists() and path.is_file(),
        "parsed": False,
        "format": "unknown",
        "outcome": "unknown",
        "error": None,
    }

    if not result["exists"]:
        result["error"] = f"Result file not found: {path}"
        return result

    text = ""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        result["error"] = str(exc)
        return result

    try:
        tree = ET.parse(str(path))
        root = tree.getroot()
        result["format"] = "xml"
        result["parsed"] = True
        result["outcome"] = _extract_xml_signal(root)
        return result
    except ET.ParseError:
        pass
    except Exception as exc:
        result["error"] = str(exc)
        return result

    result["format"] = "text"
    result["parsed"] = True
    result["outcome"] = _normalise_status(text)
    return result
