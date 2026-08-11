from __future__ import annotations

from pathlib import Path

import pytest

from easa_erules.contract import Status, ToolError
from easa_erules.input.package import OpcPackage
from easa_erules.model import (
    AssetCollection,
    FigureNode,
    ParagraphNode,
    ReferenceIndex,
    RegulationDocument,
    RegulationRequirement,
    RegulationSection,
    TableNode,
    TextNode,
)
from easa_erules.parser import EasaDocumentParser, ParseResult
from easa_erules.search.indexer import build_index, sha256_file
from easa_erules.search.query import search

FIXTURE = Path("tests/fixtures/cs-vla-sample.xml")


@pytest.fixture
def indexed(tmp_path: Path) -> Path:
    result = EasaDocumentParser(OpcPackage.from_file(FIXTURE)).parse()
    cell = ParagraphNode(children=[TextNode(text="unique table payload")])
    result.document.children[0].add_child(TableNode(rows=[[[cell]]], caption="Limits"))
    db = tmp_path / "search.sqlite"
    build_index(
        result,
        db_path=db,
        document_key="cs-vla",
        source_path=FIXTURE,
        source_sha256=sha256_file(FIXTURE),
    )
    return db


def test_pagination_total_filter_browse_and_table_text(indexed: Path):
    browse = search(
        indexed,
        "",
        limit=1,
        material_categories=["certification_specification"],
    )
    assert browse.total == 2
    assert len(browse.hits) == 1
    hit = search(indexed, "unique table payload").hits[0]
    assert hit.designation == "CS-VLA.303"
    assert hit.has_table is True


def test_invalid_filter_is_explicit_error(indexed: Path):
    with pytest.raises(ToolError) as exc:
        search(indexed, "x", material_categories=["invalid"])
    assert exc.value.status is Status.ERROR


@pytest.fixture
def structured_index(tmp_path: Path) -> Path:
    document = RegulationDocument(id="doc", document_id="cs-x", title="Structured")
    first_section = RegulationSection(id="branch-a", title="SUBPART A", level=1)
    first = RegulationRequirement(id="r1", designation="CS-X.1", title="Alpha title")
    first.add_child(ParagraphNode(children=[TextNode(text="shared collision body")]))
    first.add_child(FigureNode(image_path="asset.png", caption="Figure alpha"))
    second_section = RegulationSection(id="branch-b", title="SUBPART B", level=1)
    second = RegulationRequirement(id="r2", designation="CS-X.2", title="Beta title")
    second.add_child(ParagraphNode(children=[TextNode(text="shared collision body")]))
    appendix = RegulationSection(id="appendix-a", title="Appendix A", level=1)
    appendix_rule = RegulationRequirement(id="r3", designation="CS-X.A.1", title="Appendix item")
    document.add_children(
        [first_section, first, second_section, second, appendix, appendix_rule]
    )
    parsed = ParseResult(document, AssetCollection(), ReferenceIndex(), [], [])
    db = tmp_path / "structured.sqlite"
    build_index(parsed, db_path=db, document_key="cs-x")
    return db


def test_subtree_scope_fields_features_structure_and_exact_designation(structured_index: Path):
    scoped = search(structured_index, "shared collision", within_node_id="branch-a")
    assert scoped.total == 1
    assert scoped.hits[0].node_id == "r1"

    body = search(structured_index, "shared collision", fields=["body"])
    title = search(structured_index, "shared collision", fields=["title"])
    assert body.total == 2
    assert title.total == 0

    figures = search(structured_index, "", has_figure=True)
    assert figures.total == 1 and figures.hits[0].has_figure
    appendix = search(structured_index, "", structure_kinds=["appendix"])
    assert appendix.total == 1 and appendix.hits[0].node_id == "r3"

    exact = search(structured_index, "CS X 2")
    assert exact.hits[0].designation == "CS-X.2"


def test_offset_and_facets_use_total_before_pagination(structured_index: Path):
    page = search(
        structured_index,
        "",
        material_categories=["certification_specification"],
        limit=1,
        offset=1,
    )
    assert page.total == 3
    assert len(page.hits) == 1
    assert page.offset == 1
    assert page.facets["material_categories"] == {"certification_specification": 3}
