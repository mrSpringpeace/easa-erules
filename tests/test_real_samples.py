"""Smoke tests for real EASA publications.

Uses checked-in XML under tests/real_samples/ when present.
Optional live re-fetch: EASA_ERULES_LIVE=1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from easa_erules.input.package import OpcPackage
from easa_erules.parser import EasaDocumentParser
from easa_erules.render import render_html, render_json, render_markdown
from easa_erules.validation import validate_document

REAL_DIR = Path("tests/real_samples")
LIVE = os.environ.get("EASA_ERULES_LIVE", "").strip() in {"1", "true", "yes"}


def _local_real_files() -> list[Path]:
    if not REAL_DIR.is_dir():
        return []
    return sorted(REAL_DIR.glob("*.xml")) + sorted(REAL_DIR.glob("*.docx"))


@pytest.mark.parametrize(
    "path",
    _local_real_files(),
    ids=lambda p: p.name if isinstance(p, Path) else str(p),
)
def test_real_sample_parse_validate_convert(path: Path):
    """parse → validate → markdown/json/html smoke on real EAR XML."""
    result = EasaDocumentParser(OpcPackage.from_file(path)).parse()
    assert result.document is not None
    assert result.source_topic_count > 0

    report = validate_document(
        result.document,
        result.assets,
        result.references,
        parse_warnings=result.warnings,
        unknown_elements=result.unknown_elements,
        source_topic_count=result.source_topic_count,
    )
    # Core smoke: parse + structure + topic count alignment.
    # Designation quality: unique opaque ERulesIds from export customXml.
    assert report.topics >= 1 or report.paragraphs >= 1
    assert not report.topic_count_mismatch
    assert report.topics == result.source_topic_count or result.source_topic_count == 0
    assert report.duplicate_erules_ids == []
    # Document-level export / core metadata present on official packages
    assert result.document.title
    assert (result.document.easa_metadata or {}).get("source_title") or (
        result.document.metadata or {}
    ).get("core_properties")

    md = render_markdown(result.document, split_by_rule=True)
    assert "index.md" in md or len(md) >= 1
    js = render_json(result.document, result.assets, result.references)
    assert "document" in js
    html = render_html(result.document)
    assert next(iter(html.values())).startswith("<!DOCTYPE html>")


@pytest.mark.skipif(not _local_real_files(), reason="No XML in tests/real_samples/")
def test_real_samples_present():
    files = _local_real_files()
    names = {p.name for p in files}
    # Prefer at least CS-VLA as baseline
    assert names, "expected real sample XML files"


@pytest.mark.skipif(not LIVE, reason="Set EASA_ERULES_LIVE=1 for network fetch smoke")
@pytest.mark.parametrize("doc_id,min_topics", [("cs-vla", 10), ("cs-25", 50)])
def test_live_fetch_smoke(
    doc_id: str,
    min_topics: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Optional live fetch + parse (network required). Includes CS-25 coverage."""
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    from easa_erules.sources import EasaDownloader

    with EasaDownloader(cache_root=tmp_path) as dl:
        fetched = dl.fetch(doc_id)
    assert fetched.source_path.exists()
    result = EasaDocumentParser(OpcPackage.from_file(fetched.source_path)).parse()
    assert result.source_topic_count > min_topics
    report = validate_document(
        result.document,
        result.assets,
        result.references,
        source_topic_count=result.source_topic_count,
    )
    assert report.topics > min_topics
    assert report.duplicate_erules_ids == []
    assert result.document.title
