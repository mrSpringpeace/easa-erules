"""Cross-references written as plain text become graph edges."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import require_sample

from easa_erules.model import (
    HeadingNode,
    InternalReferenceNode,
    ParagraphNode,
    RegulationDocument,
    RegulationRequirement,
    TextNode,
)
from easa_erules.normalize.refdetect import detect_text_references, find_designations
from easa_erules.parsing import parse_any

FIXTURE = Path("tests/fixtures/cs-vla-sample.xml")


def _para(*texts: str) -> ParagraphNode:
    para = ParagraphNode()
    for text in texts:
        para.add_child(TextNode(text=text))
    return para


def _rule(designation: str, *paragraphs: ParagraphNode) -> RegulationRequirement:
    rule = RegulationRequirement()
    rule.designation = designation
    for para in paragraphs:
        rule.add_child(para)
    return rule


def _doc(*children: object) -> RegulationDocument:
    doc = RegulationDocument()
    for child in children:
        doc.add_child(child)
    return doc


def _refs(node: object) -> list[InternalReferenceNode]:
    found: list[InternalReferenceNode] = []

    def walk(n: object) -> None:
        if isinstance(n, InternalReferenceNode):
            found.append(n)
        for child in getattr(n, "children", []) or []:
            walk(child)

    walk(node)
    return found


def test_find_designations_recognises_easa_forms():
    text = "See CS-VLA 303, CS 23.2000, AMC1 CS-23.2010 and AMC VLA 21(c) for detail."
    found = [d for _s, _e, d in find_designations(text)]
    assert found == ["CS-VLA.303", "CS-23.2000", "AMC1 CS-23.2010", "AMC VLA 21(c)"]


def test_detects_reference_in_running_text():
    doc = _doc(_rule("CS-VLA.307", _para("Compliance must be shown with CS-VLA 303 loads.")))
    assert detect_text_references(doc) == 1

    refs = _refs(doc)
    assert len(refs) == 1
    assert refs[0].target_designation == "CS-VLA.303"
    assert refs[0].metadata["detected"] is True


def test_designation_split_across_word_runs_is_still_found():
    """Word splits runs arbitrarily; a reference must survive that."""
    doc = _doc(_rule("CS-VLA.307", _para("as required by ", "CS-VLA ", "303", " above.")))
    assert detect_text_references(doc) == 1
    assert _refs(doc)[0].target_designation == "CS-VLA.303"


def test_text_is_preserved_exactly():
    original = "Compliance with CS-VLA 303 is required."
    rule = _rule("CS-VLA.307", _para(original))
    detect_text_references(_doc(rule))
    assert rule.children[0].get_text() == original


def test_rule_does_not_reference_itself():
    doc = _doc(_rule("CS-VLA.303", _para("CS-VLA 303 Factor of safety")))
    assert detect_text_references(doc) == 0
    assert _refs(doc) == []


def test_undesignated_nested_section_keeps_parent_designation():
    """Otherwise the enclosing rule starts 'referencing' itself through a subsection."""
    from easa_erules.model import RegulationSection

    section = RegulationSection()
    section.add_child(_para("as stated in CS-VLA 303 above"))
    rule = _rule("CS-VLA.303")
    rule.add_child(section)

    assert detect_text_references(_doc(rule)) == 0


def test_headings_are_not_linkified():
    heading = HeadingNode()
    heading.add_child(TextNode(text="CS-VLA 303 Factor of safety"))
    rule = _rule("CS-VLA.307")
    rule.add_child(heading)

    assert detect_text_references(_doc(rule)) == 0


def test_existing_reference_nodes_are_left_alone():
    """A reference marked up in the source must not be wrapped a second time."""
    ref = InternalReferenceNode(text="CS-VLA 303", target_designation="CS-VLA.303")
    para = ParagraphNode()
    para.add_child(TextNode(text="See "))
    para.add_child(ref)
    rule = _rule("CS-VLA.307", para)

    assert detect_text_references(_doc(rule)) == 0
    assert _refs(rule) == [ref]


def test_base_designation_strips_subparagraph_markers():
    """Text cites CS-23.2240(a); only CS-23.2240 is a topic to resolve against."""
    from easa_erules.parser.document import base_designation

    assert base_designation("CS-23.2240(a)") == "CS-23.2240"
    assert base_designation("CS-23.2240(a)(1)") == "CS-23.2240"
    assert base_designation("AMC1 CS-23.2010(b)") == "AMC1 CS-23.2010"
    # Nothing to strip: the caller must not treat this as an alternative lookup
    assert base_designation("CS-23.2240") == ""
    assert base_designation("") == ""


def test_fixture_still_parses_with_detection_enabled():
    result = parse_any(FIXTURE)
    assert result.document is not None
    assert result.source_topic_count > 0


@pytest.mark.real_sample
def test_real_document_produces_resolved_reference_edges():
    """Running text cites CS 23.2240(a); resolution falls back to CS-23.2240."""
    path = require_sample(Path("tests/real_samples/cs-23.xml"))
    result = parse_any(path)
    refs = _refs(result.document)

    assert refs, "expected cross-references in CS-23"
    resolved = [r for r in refs if r.target_id]
    assert resolved, "expected at least some references to resolve to a topic"

    designations = {r.target_designation for r in resolved}
    assert any(d.startswith("CS-23.") for d in designations)


# --- CS-ETSO --------------------------------------------------------------------
# Measured on CS-ETSO Amdt 17 (fetched 2026-11-06): 324 ETSO citations detected,
# 263 resolve. The rest name another revision ("ETSO-C113" vs the catalogued
# "ETSO-C113b") or an ETSO not in this amendment, and stay unresolved on purpose.
# Detection in cs-vla, cs-22, cs-23 (Amdt 5 and 6), cs-lsa, uas-rules: identical.


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("in accordance with ETSO-C6e and ETSO-2C521.", ["ETSO-C6e", "ETSO-2C521"]),
        ("see ETSO-C44c A1, paragraph 3", ["ETSO-C44c A1"]),
        ("(ETSO-C112d)", ["ETSO-C112d"]),
        ("ETSO-C44c A320 installations", ["ETSO-C44c"]),  # not an amendment suffix
        ("ETSO authorisation holders", []),
        ("ETSO-Cxx", []),
    ],
)
def test_etso_citations(text, expected):
    assert [hit[2] for hit in find_designations(text, authority="EASA")] == expected


def test_unamended_citation_resolves_to_the_only_amendment():
    from easa_erules.parser.document import amended_etso_target

    index = {"ETSO-C146E-A1": "c146e-a1", "ETSO-C113B": "c113b", "ETSO-C5F": "c5f"}
    assert amended_etso_target("ETSO-C146E", index) == "c146e-a1"
    # Another revision letter is another ETSO:
    assert amended_etso_target("ETSO-C113", index) is None
    # Already amended, or not an ETSO: nothing to infer.
    assert amended_etso_target("ETSO-C146E-A1", index) is None
    assert amended_etso_target("CS-23.2000", index) is None
    # Two amendments of one ETSO: ambiguous, not guessed.
    index["ETSO-C146E-A2"] = "c146e-a2"
    assert amended_etso_target("ETSO-C146E", index) is None
