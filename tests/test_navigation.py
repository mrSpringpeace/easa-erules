from __future__ import annotations

from easa_erules.model import RegulationDocument, RegulationRequirement, RegulationSection
from easa_erules.navigation import build_navigation


def test_flat_sections_form_deterministic_tree_and_topics_keep_order():
    doc = RegulationDocument(id="doc", title="Test")
    subpart = RegulationSection(id="subpart-b", title="SUBPART B – FLIGHT", level=1)
    chapter = RegulationSection(id="chapter-1", title="CHAPTER 1", level=3)
    first = RegulationRequirement(id="r1", designation="CS-X.1", title="One")
    second = RegulationRequirement(id="r2", designation="CS-X.2", title="Two")
    doc.add_children([subpart, first, chapter, second])
    navigation = build_navigation(doc)
    assert [node.designation for node in navigation.navigable] == ["CS-X.1", "CS-X.2"]
    assert navigation.breadcrumb_by_id["r2"][-2]["id"] == "chapter-1"
    assert all(node["node_type"] != "paragraph" for node in navigation.outline)


def test_appendix_and_definitions_classification():
    doc = RegulationDocument(id="doc")
    doc.add_children(
        [
            RegulationSection(id="a", title="Appendix A", level=1),
            RegulationSection(id="d", title="Definitions", level=1),
        ]
    )
    outline = build_navigation(doc).outline
    kinds = [outline[0]["kind"], outline[0]["children"][0]["kind"]]
    assert kinds == ["appendix", "definitions"]
