"""Unit tests for EASA eRules parser."""

import pytest
from lxml import etree

from easa_erules.input.package import OpcPackage
from easa_erules.parser import parse_easa_document
from easa_erules.model import (
    RegulationDocument,
    RegulationRequirement,
    ParagraphNode,
    HeadingNode,
    TextNode,
    BoldNode,
    ItalicNode,
    SuperscriptNode,
    SubscriptNode,
)


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
    
    # Check text content
    first_para = paragraphs[0]
    assert "factor of safety" in first_para.get_text().lower()


def test_heading_parsed(parsed_document):
    """Test that headings are parsed."""
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
    # Document level
    assert "easa" in parsed_document.metadata
    assert parsed_document.metadata["easa"]["erules_id"] == "ERULES-CS-VLA-001"
    
    # Requirement level
    req_303 = next(c for c in parsed_document.children if c.designation == "CS-VLA.303")
    assert "easa" in req_303.metadata
    assert req_303.metadata["easa"]["typeOfContent"] == "Certification Specification"


def test_render_markdown(parsed_document):
    """Test Markdown rendering."""
    from easa_erules.render import render_markdown
    
    files = render_markdown(parsed_document)
    assert len(files) == 1
    content = list(files.values())[0]
    
    assert "CS-VLA.303: CS-VLA.303 Factor of safety" in content
    assert "factor of safety" in content.lower()
    assert "Subpart A - General" in content


def test_render_markdown_split(parsed_document):
    """Test split Markdown rendering."""
    from easa_erules.render import render_markdown
    
    files = render_markdown(parsed_document, split_by_rule=True)
    assert "index.md" in files
    assert "rules/cs-vla-303.md" in files
    assert "rules/cs-vla-305.md" in files
    
    # Check index
    index = files["index.md"]
    assert "CS-VLA.303: CS-VLA.303 Factor of safety" in index
    assert "rules/cs-vla-303.md" in index
    
    # Check rule file
    rule_303 = files["rules/cs-vla-303.md"]
    assert "rule: CS-VLA.303" in rule_303
    assert "factor of safety" in rule_303.lower()


def test_render_json(parsed_document):
    """Test JSON rendering."""
    from easa_erules.render import render_json
    
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
    
    # Should have bold wrapping italic (or vice versa)
    italic_nodes = [c for c in para.children if isinstance(c, ItalicNode)]
    assert len(italic_nodes) == 1
    # The text should be "bold and italic" 
    assert italic_nodes[0].text == "bold and italic"
    # And it should have a bold child
    bold_children = [c for c in italic_nodes[0].children if isinstance(c, BoldNode)]
    assert len(bold_children) == 1


def test_render_markdown_inline_formatting(formatting_document):
    """Test Markdown rendering with inline formatting."""
    from easa_erules.render import render_markdown
    
    files = render_markdown(formatting_document)
    content = list(files.values())[0]
    
    assert "**bold text**" in content
    assert "*italic text*" in content
    assert "<sup>2</sup>" in content
    assert "<sub>1</sub>" in content
    assert "***bold and italic***" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])