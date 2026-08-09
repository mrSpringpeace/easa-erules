"""Tests for HTML render, refs graph, and normalize pipeline."""

from __future__ import annotations

from pathlib import Path

from easa_erules.input.package import OpcPackage
from easa_erules.model import ListItemNode, ListNode, ParagraphNode, RegulationDocument, TextNode
from easa_erules.model.graph import lookup_refs
from easa_erules.normalize import normalize_document
from easa_erules.parser import EasaDocumentParser, parse_easa_document
from easa_erules.render import render_html


def test_render_html_sample():
    doc = parse_easa_document(OpcPackage.from_file("tests/fixtures/cs-vla-sample.xml"))
    files = render_html(doc)
    assert len(files) == 1
    html = next(iter(files.values()))
    assert html.startswith("<!DOCTYPE html>")
    assert "CS-VLA.303" in html
    assert "factor of safety" in html.lower()
    assert "<h1>" in html


def test_refs_graph_links_fixture():
    result = EasaDocumentParser(OpcPackage.from_file("tests/fixtures/links.xml")).parse()
    node = lookup_refs(result.document, "CS-TEST.300")
    assert node is not None
    targets = {e.target_designation for e in node.references}
    assert "CS-TEST.305" in targets

    target = lookup_refs(result.document, "CS-TEST.305")
    assert target is not None
    sources = {e.source_designation for e in target.referenced_by}
    assert "CS-TEST.300" in sources

    tree = node.to_text_tree()
    assert "references →" in tree
    assert "referenced-by →" in tree


def test_normalize_whitespace_and_numbering():
    doc = RegulationDocument(title="T", document_id="D")
    para = ParagraphNode()
    para.add_child(TextNode(text="  hello   world  "))
    doc.add_child(para)
    lst = ListNode(ordered=True)
    for _ in range(2):
        item = ListItemNode()
        item.add_child(TextNode(text="x"))
        lst.add_child(item)
    doc.add_child(lst)

    normalize_document(doc)
    assert para.children[0].text == "hello   world".replace("  ", " ").strip() or "hello world"
    # collapse runs → single spaces, strip edges
    assert para.children[0].text == "hello world"
    assert [c.number for c in lst.children] == [1, 2]


def test_convert_html_cli_format(tmp_path: Path):
    # lightweight: render path only (CLI covered indirectly)
    doc = parse_easa_document(OpcPackage.from_file("tests/fixtures/inline-formatting.xml"))
    files = render_html(doc)
    content = next(iter(files.values()))
    assert "<strong>" in content or "<em>" in content
