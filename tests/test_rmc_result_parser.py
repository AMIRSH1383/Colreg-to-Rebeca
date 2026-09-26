"""Unit tests for rmc_result_parser.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

from rmc_result_parser import parse_rmc_result_file


def test_parse_xml_status_satisfied() -> None:
    xml = """<result><verification status=\"satisfied\" /></result>"""
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        p = Path(td) / "result.xml"
        p.write_text(xml, encoding="utf-8")
        parsed = parse_rmc_result_file(str(p))

    assert parsed["parsed"] is True
    assert parsed["format"] == "xml"
    assert parsed["outcome"] == "satisfied"


def test_parse_xml_holds_false_is_cex() -> None:
    xml = """<result><property holds=\"false\" /></result>"""
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        p = Path(td) / "result.xml"
        p.write_text(xml, encoding="utf-8")
        parsed = parse_rmc_result_file(str(p))

    assert parsed["parsed"] is True
    assert parsed["format"] == "xml"
    assert parsed["outcome"] == "cex"


def test_parse_xml_result_satisfied_with_empty_counterexample_trace() -> None:
        xml = """
        <analysis>
            <result>satisfied</result>
            <summary>counterexample section present</summary>
            <counter-example-trace />
        </analysis>
        """
        with tempfile.TemporaryDirectory(dir=Path.home()) as td:
                p = Path(td) / "result.xml"
                p.write_text(xml, encoding="utf-8")
                parsed = parse_rmc_result_file(str(p))

        assert parsed["parsed"] is True
        assert parsed["format"] == "xml"
        assert parsed["outcome"] == "satisfied"


def test_parse_xml_nonempty_counterexample_trace_is_cex() -> None:
        xml = """
        <analysis>
            <result>satisfied</result>
            <counter-example-trace>
                <state id="1" />
            </counter-example-trace>
        </analysis>
        """
        with tempfile.TemporaryDirectory(dir=Path.home()) as td:
                p = Path(td) / "result.xml"
                p.write_text(xml, encoding="utf-8")
                parsed = parse_rmc_result_file(str(p))

        assert parsed["parsed"] is True
        assert parsed["format"] == "xml"
        assert parsed["outcome"] == "cex"


def test_parse_text_counterexample_is_cex() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        p = Path(td) / "result.txt"
        p.write_text("Counterexample found", encoding="utf-8")
        parsed = parse_rmc_result_file(str(p))

    assert parsed["parsed"] is True
    assert parsed["format"] == "text"
    assert parsed["outcome"] == "cex"


def test_missing_file_returns_error() -> None:
    with tempfile.TemporaryDirectory(dir=Path.home()) as td:
        p = Path(td) / "missing.xml"
        parsed = parse_rmc_result_file(str(p))

    assert parsed["exists"] is False
    assert parsed["parsed"] is False
    assert "not found" in str(parsed["error"]).lower()
