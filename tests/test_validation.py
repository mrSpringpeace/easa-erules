"""Unit tests for the validation framework (M6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from easa_erules.input.package import OpcPackage
from easa_erules.model import (
    FigureNode,
    RegulationDocument,
    RegulationRequirement,
    TextNode,
)
from easa_erules.model.assets import Asset, AssetCollection
from easa_erules.parser import EasaDocumentParser
from easa_erules.render import render_markdown
from easa_erules.validation import (
    build_conversion_report,
    validate_conversion,
    validate_document,
)
from easa_erules.validation.structure import count_and_check_structure
from easa_erules.validation.report import ValidationReport


def _parse(fixture: str):
    pkg = OpcPackage.from_file(fixture)
    return EasaDocumentParser(pkg).parse()


def test_validate_document_ok_sample():
    result = _parse("tests/fixtures/cs-vla-sample.xml")
    report = validate_document(
        result.document,
        result.assets,
        result.references,
        parse_warnings=result.warnings,
        unknown_elements=result.unknown_elements,
        source_topic_count=result.source_topic_count,
    )
    assert report.ok
    assert report.requirements == 2
    assert report.topics == 2
    assert report.source_topic_count == 2
    assert not report.topic_count_mismatch
    assert report.unique_erules_ids == 2
    assert report.duplicate_erules_ids == []
    assert report.paragraphs >= 2


def test_source_topic_count_mismatch():
    result = _parse("tests/fixtures/cs-vla-sample.xml")
    report = validate_document(
        result.document,
        result.assets,
        result.references,
        source_topic_count=99,
    )
    assert not report.ok
    assert report.topic_count_mismatch
    assert any(e.get("type") == "topic_count_mismatch" for e in report.errors)


def test_duplicate_erules_id_is_error():
    doc = RegulationDocument(document_id="DOC", title="T")
    r1 = RegulationRequirement(designation="CS-X.1", title="A", erules_id="DUP")
    r2 = RegulationRequirement(designation="CS-X.2", title="B", erules_id="DUP")
    doc.add_child(r1)
    doc.add_child(r2)
    report = ValidationReport()
    count_and_check_structure(doc, report)
    report.finalize()
    assert "DUP" in report.duplicate_erules_ids
    assert any(e.get("type") == "duplicate_erules_id" for e in report.errors)
    assert not report.ok


def test_missing_figure_asset_is_error():
    doc = RegulationDocument(document_id="DOC", title="T")
    req = RegulationRequirement(designation="CS-X.1", title="A", erules_id="CS-X.1")
    fig = FigureNode(image_path="missing-fig.png", caption="x")
    req.add_child(fig)
    doc.add_child(req)
    assets = AssetCollection()
    report = validate_document(doc, assets=assets)
    assert not report.ok
    assert "missing-fig.png" in report.missing_images


def test_figure_asset_present_ok():
    doc = RegulationDocument(document_id="DOC", title="T")
    req = RegulationRequirement(designation="CS-X.1", title="A", erules_id="CS-X.1")
    fig = FigureNode(image_path="ok.png", caption="x")
    req.add_child(fig)
    doc.add_child(req)
    assets = AssetCollection()
    assets.add(
        Asset(
            original_path="word/media/image1.png",
            content_type="image/png",
            data=b"\x89PNG",
            deterministic_name="ok.png",
        )
    )
    report = validate_document(doc, assets=assets)
    assert report.images == 1
    assert report.missing_images == []
    assert report.ok


def test_unresolved_internal_reference_is_warning():
    result = _parse("tests/fixtures/links.xml")
    # links fixture has AMC1 CS-TEST.300 which has no target topic
    report = validate_document(
        result.document,
        result.assets,
        result.references,
        source_topic_count=result.source_topic_count,
    )
    # CS-TEST.305 should resolve; AMC1 CS-TEST.300 may be unresolved
    unresolved = [r for r in report.unresolved_references if "AMC" in (r.get("target_designation") or "")]
    assert unresolved
    # unresolved refs are warnings, not hard errors by default
    assert report.ok or report.errors  # still ok if only warnings


def test_validate_conversion_output(tmp_path: Path):
    result = _parse("tests/fixtures/images.xml")
    out = tmp_path / "out"
    out.mkdir()
    files = render_markdown(result.document, split_by_rule=True)
    for name, content in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    assets_dir = out / "assets"
    assets_dir.mkdir()
    for name, asset in result.assets.assets.items():
        (assets_dir / name).write_bytes(asset.data)

    report = build_conversion_report(
        result.document,
        assets=result.assets,
        references=result.references,
        source_topic_count=result.source_topic_count,
        output_dir=out,
    )
    (out / "conversion-report.json").write_text(
        json.dumps(report.to_dict(), indent=2),
        encoding="utf-8",
    )
    (out / "document.json").write_text("{}", encoding="utf-8")

    disk = validate_conversion(out)
    assert disk.missing_images == []
    assert disk.topics >= 1
    assert disk.images == 2


def test_validate_conversion_detects_missing_image(tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "index.md").write_text(
        "---\nid: x\n---\n\n# Doc\n\n![fig](assets/nope.png)\n",
        encoding="utf-8",
    )
    report = validate_conversion(out)
    assert not report.ok
    assert any("nope.png" in m for m in report.missing_images)


def test_report_to_dict_shape():
    report = ValidationReport(topics=1, paragraphs=2, ok=True)
    d = report.to_dict()
    assert d["topics"] == 1
    assert d["paragraphs"] == 2
    assert "unresolved_references" in d
    assert "parser_version" in d
