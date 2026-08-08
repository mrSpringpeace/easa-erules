"""Golden tests: parse(fixture) → render == expected artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from easa_erules.input.package import OpcPackage
from easa_erules.parser import EasaDocumentParser
from easa_erules.render import render_json, render_markdown
from easa_erules.validation import validate_document

GOLDEN_ROOT = Path("tests/golden")


def _cases() -> list[Path]:
    if not GOLDEN_ROOT.is_dir():
        return []
    return sorted(p for p in GOLDEN_ROOT.iterdir() if p.is_dir() and (p / "case.json").exists())


@pytest.mark.parametrize("case_dir", _cases(), ids=lambda p: p.name)
def test_golden_markdown(case_dir: Path):
    """Rendered Markdown matches frozen golden files."""
    meta = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    pkg = OpcPackage.from_file(meta["fixture"])
    result = EasaDocumentParser(pkg).parse()
    files = render_markdown(result.document, split_by_rule=bool(meta.get("split")))

    if meta.get("split"):
        expected_root = case_dir / "expected"
        expected_files = {
            str(p.relative_to(expected_root)): p.read_text(encoding="utf-8")
            for p in expected_root.rglob("*")
            if p.is_file()
        }
        assert set(files.keys()) == set(expected_files.keys())
        for name, content in files.items():
            assert content == expected_files[name], f"Mismatch in {name}"
    else:
        expected = (case_dir / "expected.md").read_text(encoding="utf-8")
        actual = next(iter(files.values()))
        assert actual == expected


@pytest.mark.parametrize("case_dir", _cases(), ids=lambda p: p.name)
def test_golden_json(case_dir: Path):
    """Rendered JSON AST matches frozen golden JSON."""
    meta = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    pkg = OpcPackage.from_file(meta["fixture"])
    result = EasaDocumentParser(pkg).parse()
    actual = render_json(result.document, result.assets, result.references)
    expected = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    assert actual == expected


@pytest.mark.parametrize("case_dir", _cases(), ids=lambda p: p.name)
def test_golden_validation_report(case_dir: Path):
    """Validation report counts/status match frozen golden report."""
    meta = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    pkg = OpcPackage.from_file(meta["fixture"])
    result = EasaDocumentParser(pkg).parse()
    report = validate_document(
        result.document,
        result.assets,
        result.references,
        parse_warnings=result.warnings,
        unknown_elements=result.unknown_elements,
        source_topic_count=result.source_topic_count,
    )
    expected = json.loads((case_dir / "expected-report.json").read_text(encoding="utf-8"))
    # Compare stable structural fields (warnings order may vary in future)
    for key in (
        "ok",
        "topics",
        "paragraphs",
        "tables",
        "images",
        "requirements",
        "sections",
        "unique_erules_ids",
        "duplicate_erules_ids",
        "source_topic_count",
        "topic_count_mismatch",
    ):
        assert report.to_dict()[key] == expected[key], f"{case_dir.name}: field {key}"
