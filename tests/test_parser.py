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
)


@pytest.fixture
def sample_package():
    """Load the sample CS-VLA package."""
    return OpcPackage.from_file("tests/fixtures/cs-vla-sample.xml")


@pytest.fixture
def parsed_document(sample_package):
    """Parse the sample document."""
    return parse_easa_document(sample_package)


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])