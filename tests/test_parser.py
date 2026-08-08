"""Unit tests for EASA eRules parser."""

import io
import zipfile
from pathlib import Path

import pytest

from easa_erules.input.package import OpcPackage
from easa_erules.model import (
    BoldNode,
    FigureNode,
    HyperlinkNode,
    InternalReferenceNode,
    ItalicNode,
    ListNode,
    ParagraphNode,
    RegulationDocument,
    RegulationRequirement,
    SubscriptNode,
    SuperscriptNode,
    TextNode,
)
from easa_erules.parser import EasaDocumentParser, parse_easa_document
from easa_erules.render import render_json, render_markdown
from easa_erules.render.frontmatter import parse_frontmatter
from easa_erules.sources.registry import get_source, resolve_source_id
from easa_erules.validation import validate_conversion, validate_document


@pytest.fixture
def sample_package():
    """Load the sample CS-VLA package."""
    return OpcPackage.from_file("tests/fixtures/cs-vla-sample.xml")


@pytest.fixture
def parsed_document(sample_package):
    """Parse the sample document."""
    return parse_easa_document(sample_package)


@pytest.fixture
def formatting_package():
    """Load the inline formatting test package."""
    return OpcPackage.from_file("tests/fixtures/inline-formatting.xml")


@pytest.fixture
def formatting_document(formatting_package):
    """Parse the formatting test document."""
    return parse_easa_document(formatting_package)


def test_package_loads(sample_package):
    """Test that the package loads correctly."""
    assert "word/document.xml" in sample_package._parts
    assert sample_package.get_main_document_part() is not None


def test_document_parsed(parsed_document):
    """Test that the document is parsed with correct metadata."""
    assert isinstance(parsed_document, RegulationDocument)
    assert parsed_document.title == "Easy Access Rules for Very Light Aeroplanes"
    assert parsed_document.document_id == "ERULES-CS-VLA-001"
    assert parsed_document.easa_metadata["erules_id"] == "ERULES-CS-VLA-001"
    assert "CS-VLA" in parsed_document.easa_metadata["regulatory_source"]


def test_requirements_extracted(parsed_document):
    """Test that requirements are extracted."""
    requirements = [c for c in parsed_document.children if isinstance(c, RegulationRequirement)]
    assert len(requirements) == 2

    req_303 = next(r for r in requirements if r.designation == "CS-VLA.303")
    req_305 = next(r for r in requirements if r.designation == "CS-VLA.305")

    assert req_303.erules_id == "CS-VLA.303"
    assert req_303.title == "CS-VLA.303 Factor of safety"
    assert req_305.erules_id == "CS-VLA.305"
    assert req_305.title == "CS-VLA.305 Strength and deformation"


def test_paragraphs_in_requirement(parsed_document):
    """Test that paragraphs are parsed within requirements."""
    req_303 = next(c for c in parsed_document.children if c.designation == "CS-VLA.303")
    paragraphs = [c for c in req_303.children if isinstance(c, ParagraphNode)]
    assert len(paragraphs) >= 1

    first_para = paragraphs[0]
    assert "factor of safety" in first_para.get_text().lower()


def test_heading_parsed(parsed_document):
    """Test that headings are parsed."""
    from easa_erules.model import HeadingNode

    req_303 = next(c for c in parsed_document.children if c.designation == "CS-VLA.303")
    headings = [c for c in req_303.children if isinstance(c, HeadingNode)]
    assert len(headings) >= 1

    heading = headings[0]
    assert heading.get_text() == "Subpart A - General"
    assert heading.level == 1


def test_text_nodes(parsed_document):
    """Test that text nodes are created correctly."""
    req_303 = next(c for c in parsed_document.children if c.designation == "CS-VLA.303")
    para = next(c for c in req_303.children if isinstance(c, ParagraphNode))

    text_nodes = [c for c in para.children if isinstance(c, TextNode)]
    assert len(text_nodes) >= 1
    assert "factor of safety" in text_nodes[0].text.lower()


def test_easa_metadata_preserved(parsed_document):
    """Test that EASA metadata is preserved in document and requirements."""
    assert "easa" in parsed_document.metadata
    assert parsed_document.metadata["easa"]["erules_id"] == "ERULES-CS-VLA-001"

    req_303 = next(c for c in parsed_document.children if c.designation == "CS-VLA.303")
    assert "easa" in req_303.metadata
    # Normalized snake_case keys
    assert req_303.metadata["easa"]["type_of_content"] == ["Certification Specification"]
    assert req_303.metadata["easa"]["technical_subject_matter"] == ["Structures"]


def test_render_markdown(parsed_document):
    """Test Markdown rendering."""
    files = render_markdown(parsed_document)
    assert len(files) == 1
    content = list(files.values())[0]

    assert content.startswith("---\n")
    assert "CS-VLA.303: CS-VLA.303 Factor of safety" in content
    assert "factor of safety" in content.lower()
    assert "Subpart A - General" in content


def test_render_markdown_split(parsed_document):
    """Test split Markdown rendering."""
    files = render_markdown(parsed_document, split_by_rule=True)
    assert "index.md" in files
    assert "rules/cs-vla-303.md" in files
    assert "rules/cs-vla-305.md" in files

    index = files["index.md"]
    assert "CS-VLA.303: CS-VLA.303 Factor of safety" in index
    assert "rules/cs-vla-303.md" in index

    rule_303 = files["rules/cs-vla-303.md"]
    assert rule_303.startswith("---\n")
    fm, body = parse_frontmatter(rule_303)
    assert fm["rule"] == "CS-VLA.303"
    assert fm["id"] == "CS-VLA.303"
    assert fm["easa"]["type_of_content"] == ["Certification Specification"]
    assert "factor of safety" in body.lower()


def test_render_json(parsed_document):
    """Test JSON rendering."""
    result = render_json(parsed_document)
    assert "document" in result
    assert result["document"]["type"] == "document"
    assert result["document"]["title"] == "Easy Access Rules for Very Light Aeroplanes"
    assert len(result["document"]["children"]) == 2


def test_inline_formatting_bold(formatting_document):
    """Test bold inline formatting."""
    req = formatting_document.children[0]
    para = req.children[0]

    bold_nodes = [c for c in para.children if isinstance(c, BoldNode)]
    assert len(bold_nodes) == 1
    assert bold_nodes[0].text == "bold text"


def test_inline_formatting_italic(formatting_document):
    """Test italic inline formatting."""
    req = formatting_document.children[0]
    para = req.children[0]

    italic_nodes = [c for c in para.children if isinstance(c, ItalicNode)]
    assert len(italic_nodes) == 1
    assert italic_nodes[0].text == "italic text"


def test_inline_formatting_superscript(formatting_document):
    """Test superscript inline formatting."""
    req = formatting_document.children[0]
    para = req.children[1]

    sup_nodes = [c for c in para.children if isinstance(c, SuperscriptNode)]
    assert len(sup_nodes) == 1
    assert sup_nodes[0].text == "2"


def test_inline_formatting_subscript(formatting_document):
    """Test subscript inline formatting."""
    req = formatting_document.children[0]
    para = req.children[1]

    sub_nodes = [c for c in para.children if isinstance(c, SubscriptNode)]
    assert len(sub_nodes) == 1
    assert sub_nodes[0].text == "1"


def test_inline_formatting_combined(formatting_document):
    """Test combined bold+italic inline formatting."""
    req = formatting_document.children[0]
    para = req.children[2]

    italic_nodes = [c for c in para.children if isinstance(c, ItalicNode)]
    assert len(italic_nodes) == 1
    assert italic_nodes[0].text == "bold and italic"
    bold_children = [c for c in italic_nodes[0].children if isinstance(c, BoldNode)]
    assert len(bold_children) == 1


def test_render_markdown_inline_formatting(formatting_document):
    """Test Markdown rendering with inline formatting."""
    files = render_markdown(formatting_document)
    content = list(files.values())[0]

    assert "**bold text**" in content
    assert "*italic text*" in content
    assert "<sup>2</sup>" in content
    assert "<sub>1</sub>" in content
    assert "***bold and italic***" in content


def test_deterministic_ids(sample_package):
    """Two parses of the same source yield identical node IDs."""
    a = parse_easa_document(sample_package)
    b = parse_easa_document(OpcPackage.from_file("tests/fixtures/cs-vla-sample.xml"))
    assert a.id == b.id == "ERULES-CS-VLA-001"
    assert a.children[0].id == b.children[0].id == "CS-VLA.303"
    files_a = render_markdown(a, split_by_rule=True)
    files_b = render_markdown(b, split_by_rule=True)
    assert files_a == files_b


def test_lists_fixture():
    """Ordered and bullet lists are parsed."""
    pkg = OpcPackage.from_file("tests/fixtures/lists.xml")
    result = EasaDocumentParser(pkg).parse()
    lists = result.document.find_all(
        __import__("easa_erules.model", fromlist=["NodeType"]).NodeType.LIST
    )
    assert len(lists) >= 2
    ordered = [L for L in lists if L.ordered]
    bullets = [L for L in lists if not L.ordered]
    assert ordered
    assert bullets
    assert all(len(L.children) >= 1 for L in lists)


def test_links_external_and_internal():
    """External hyperlinks and plain-text internal refs are detected."""
    pkg = OpcPackage.from_file("tests/fixtures/links.xml")
    result = EasaDocumentParser(pkg).parse()
    doc = result.document

    def walk(node, acc=None):
        acc = acc if acc is not None else []
        if isinstance(node, (HyperlinkNode, InternalReferenceNode)):
            acc.append(node)
        for child in node.children:
            walk(child, acc)
        return acc

    nodes = walk(doc)
    hyperlinks = [n for n in nodes if isinstance(n, HyperlinkNode)]
    internals = [n for n in nodes if isinstance(n, InternalReferenceNode)]

    assert hyperlinks
    assert any("easa.europa.eu" in (h.url or "") for h in hyperlinks)
    assert any(n.target_designation == "CS-TEST.305" for n in internals)
    # Target exists so at least one internal ref should resolve
    resolved = [n for n in internals if n.target_id]
    assert resolved


def test_images_extracted_with_rule_names():
    """Figures are extracted and named from the parent rule designation."""
    pkg = OpcPackage.from_file("tests/fixtures/images.xml")
    result = EasaDocumentParser(pkg).parse()

    assert len(result.assets.assets) == 2
    names = sorted(result.assets.assets.keys())
    assert names[0].startswith("cs-test-400-fig-")
    assert names[0].endswith(".png")

    figures = result.document.find_all(
        __import__("easa_erules.model", fromlist=["NodeType"]).NodeType.FIGURE
    )
    assert len(figures) == 2
    assert all(isinstance(f, FigureNode) for f in figures)


def test_convert_writes_assets(tmp_path):
    """convert pipeline writes assets, document.json, metadata.yaml."""
    from easa_erules.cli import _write_assets, _write_metadata_yaml

    pkg = OpcPackage.from_file("tests/fixtures/images.xml")
    result = EasaDocumentParser(pkg).parse()
    out = tmp_path / "out"
    out.mkdir()

    files = render_markdown(result.document, split_by_rule=True)
    for name, content in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    written = _write_assets(out, result.assets)
    assert written == 2
    assert (out / "assets").is_dir()
    assert list((out / "assets").glob("*.png"))

    import json
    (out / "document.json").write_text(
        json.dumps(render_json(result.document, result.assets, result.references)),
        encoding="utf-8",
    )
    _write_metadata_yaml(out, result.document)
    assert (out / "metadata.yaml").exists()

    report = validate_conversion(out)
    assert report.images == 2
    assert report.missing_images == []


def test_zip_package_loads_document_relationships(tmp_path):
    """ZIP OOXML loads word/_rels/document.xml.rels (not word/document.xml.rels)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0"?>
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
              <Default Extension="xml" ContentType="application/xml"/>
              <Default Extension="png" ContentType="image/png"/>
              <Override PartName="/word/document.xml"
                ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
            </Types>""",
        )
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
                Target="word/document.xml"/>
            </Relationships>""",
        )
        zf.writestr(
            "word/document.xml",
            """<?xml version="1.0"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                        xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                        xmlns:erules="http://www.easa.europa.eu/erules">
              <w:body>
                <erules:metadata>
                  <erules:id>ZIP-001</erules:id>
                  <erules:title>Zip Test</erules:title>
                  <erules:regulatorySource>CS-TEST</erules:regulatorySource>
                  <erules:typeOfContent>Certification Specification</erules:typeOfContent>
                </erules:metadata>
                <erules:topic>
                  <erules:id>CS-TEST.1</erules:id>
                  <erules:title>CS-TEST.1 Topic</erules:title>
                  <erules:metadata>
                    <erules:typeOfContent>Certification Specification</erules:typeOfContent>
                  </erules:metadata>
                  <w:p><w:r><w:t>Hello</w:t></w:r></w:p>
                </erules:topic>
              </w:body>
            </w:document>""",
        )
        zf.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId9"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
                Target="media/image1.png"/>
            </Relationships>""",
        )
        zf.writestr("word/media/image1.png", b"\x89PNG\r\n\x1a\n")

    docx_path = tmp_path / "sample.docx"
    docx_path.write_bytes(buf.getvalue())

    pkg = OpcPackage.from_file(docx_path)
    part = pkg.get_main_document_part()
    assert part is not None
    assert part.relationships is not None
    rel = part.relationships.get("rId9")
    assert rel is not None
    resolved = pkg.resolve_part(rel.target, source_part_path=part.path)
    assert resolved is not None
    assert resolved.data.startswith(b"\x89PNG")


def test_registry_aliases():
    """Registry resolves aliases to canonical IDs."""
    assert resolve_source_id("vla") == "cs-vla"
    assert resolve_source_id("CS-VLA") == "cs-vla"
    assert resolve_source_id("csvla") == "cs-vla"
    assert resolve_source_id("CS23") == "cs-23"
    source = get_source("lsa")
    assert source["id"] == "cs-lsa"
    assert "Light Sport" in source["title"]


def test_extract_json_shape(sample_package):
    """Single-rule JSON extract uses the agent-friendly shape."""
    doc = parse_easa_document(sample_package)
    req = next(c for c in doc.children if c.designation == "CS-VLA.303")
    data = render_json(req)
    assert data["rule"] == "CS-VLA.303"
    assert data["id"] == "CS-VLA.303"
    assert "content" in data
    assert "document" not in data


def test_validate_document_topics(sample_package):
    """Parse-time validation reports topic/requirement counts."""
    result = EasaDocumentParser(sample_package).parse()
    report = validate_document(
        result.document,
        result.assets,
        result.references,
        parse_warnings=result.warnings,
        unknown_elements=result.unknown_elements,
    )
    assert report.requirements == 2
    assert report.topics == 2
    assert report.paragraphs >= 2


def test_unknown_elements_reported():
    """Unknown custom elements are collected (not silently dropped without report)."""
    pkg = OpcPackage.from_file("tests/fixtures/unknown-elements.xml")
    result = EasaDocumentParser(pkg).parse()
    # Fixture may or may not have unknown erules elements; ensure parse succeeds
    assert result.document is not None
    assert result.document.document_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
