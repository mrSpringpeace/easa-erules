"""Items the publisher prints more than once are not treated as a defect.

An AMC or GM covering several rules appears once under each of them, carrying
the same ERulesId every time. Part-21 has 25 such items across 67 occurrences.
That is how EASA publishes them — flagging it as a duplicate-id error would
fail validation on a perfectly good document.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import require_sample

from easa_erules import api
from easa_erules.model import (
    AcceptableMeansOfComplianceNode,
    ParagraphNode,
    RegulationDocument,
    TextNode,
)
from easa_erules.validation import validate_document


def _amc(erules_id: str, body: str) -> AcceptableMeansOfComplianceNode:
    node = AcceptableMeansOfComplianceNode()
    node.erules_id = erules_id
    para = ParagraphNode()
    para.add_child(TextNode(text=body))
    node.add_child(para)
    return node


def _doc(*children: object) -> RegulationDocument:
    doc = RegulationDocument()
    for child in children:
        doc.add_child(child)
    return doc


def test_identical_repeats_are_recorded_not_failed():
    doc = _doc(
        _amc("ERULES-1", "Applies to 21.A.14, 21.A.143 and 21.A.243."),
        _amc("ERULES-1", "Applies to 21.A.14, 21.A.143 and 21.A.243."),
        _amc("ERULES-1", "Applies to 21.A.14, 21.A.143 and 21.A.243."),
    )
    report = validate_document(doc)

    assert report.ok
    assert report.duplicate_erules_ids == []
    assert report.repeated_erules_ids == {"ERULES-1": 3}
    assert any(w["type"] == "repeated_erules_ids" for w in report.warnings)


def test_same_id_different_content_is_an_error():
    """Then the id no longer identifies one item, which is a real problem."""
    doc = _doc(
        _amc("ERULES-2", "One body."),
        _amc("ERULES-2", "A different body entirely."),
    )
    report = validate_document(doc)

    assert not report.ok
    assert report.duplicate_erules_ids == ["ERULES-2"]
    assert report.repeated_erules_ids == {}
    assert any(e["type"] == "conflicting_erules_id" for e in report.errors)


def test_unique_ids_produce_neither():
    doc = _doc(_amc("ERULES-3", "One."), _amc("ERULES-4", "Two."))
    report = validate_document(doc)

    assert report.ok
    assert report.duplicate_erules_ids == []
    assert report.repeated_erules_ids == {}
    assert report.unique_erules_ids == 2


def test_extract_reports_how_many_times_an_item_appears(tmp_path: Path):
    """Returning one body silently would hide that the publisher printed seven."""
    from easa_erules.util.ids import assign_deterministic_ids

    doc = _doc(
        _amc("ERULES-5", "Shared guidance."),
        _amc("ERULES-5", "Shared guidance."),
    )
    assign_deterministic_ids(doc)
    matches = api.find_rules(doc, "ERULES-5")
    assert len(matches) == 2
    # Deduplicated node ids keep the AST addressable
    assert len({m.id for m in matches}) == 2


@pytest.mark.real_sample
def test_part21_repeats_do_not_fail_validation():
    path = Path("tests/real_samples/part-21.xml")
    if not path.is_file():
        pytest.skip("part-21 sample not pinned locally")
    require_sample(path)

    from easa_erules.parsing import parse_any

    result = parse_any(path)
    report = validate_document(
        result.document,
        result.assets,
        result.references,
        source_topic_count=result.source_topic_count,
    )
    assert report.duplicate_erules_ids == []
    assert report.repeated_erules_ids
    assert report.ok
