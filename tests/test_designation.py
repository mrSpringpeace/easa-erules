"""Unit tests for regulatory designation extraction and normalization."""

from __future__ import annotations

import pytest

from easa_erules.util.slugify import (
    extract_designation,
    extract_designation_from_lines,
    extract_ed_decision,
    normalize_designation,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("CS-VLA 1 Applicability", "CS-VLA.1"),
        ("CS-VLA.303 Factor of safety", "CS-VLA.303"),
        ("CS 23.2000 Applicability and definitions", "CS-23.2000"),
        ("CS-23.2100 Mass and centre of gravity", "CS-23.2100"),
        ("AMC VLA 1 Applicability (Interpretative Material)", "AMC VLA 1"),
        ("AMC VLA 21(c) Proof of compliance", "AMC VLA 21(c)"),
        ("AMC VLA 21(d) Proof of compliance", "AMC VLA 21(d)"),
        ("AMC1 23.2000 Applicability", "AMC1 CS-23.2000"),
        ("GM1 23.2010 Accepted means of compliance", "GM1 CS-23.2010"),
        ("AMC1 CS-TEST.300", "AMC1 CS-TEST.300"),
        ("GM2 CS 23.2010 text", "GM2 CS-23.2010"),
    ],
)
def test_extract_designation_full(text: str, expected: str):
    assert extract_designation(text, require_number=True) == expected


def test_require_number_rejects_bare_document_code():
    assert extract_designation("CS-VLA is considered applicable", require_number=True) == ""
    assert extract_designation("CS-VLA is considered applicable", require_number=False) == "CS-VLA"


def test_preamble_and_toc_do_not_false_positive():
    toc = r'TOC \o "1-3" \h \z Heading 1 AMC CS related'
    assert extract_designation(toc, require_number=True) == ""
    preamble = "Preamble ED Decision 2009/003/R Amendment 1 CS-VLA 783 Amended"
    # Designation must be at the start of the title line
    assert extract_designation(preamble, require_number=True) == ""


def test_extract_from_lines_prefers_numbered():
    lines = [
        "Incorporated amendments",
        "CS-VLA 1 Applicability",
        "ED Decision 2003/18/RM",
    ]
    assert extract_designation_from_lines(lines) == "CS-VLA.1"


def test_normalize_designation_spacing():
    assert normalize_designation("CS 23.2210") == "CS-23.2210"
    assert normalize_designation("CS-VLA 1") == "CS-VLA.1"
    assert normalize_designation("AMC1  23.2100") == "AMC1 CS-23.2100"


def test_extract_ed_decision():
    assert extract_ed_decision("ED Decision 2003/18/RM") == "ED Decision 2003/18/RM"
    assert extract_ed_decision("See ED Decision 2017/013/R for details") == "ED Decision 2017/013/R"
    assert extract_ed_decision("No decision here") == ""
