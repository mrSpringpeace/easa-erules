"""Smoke tests for real EASA publications.

The publications are not stored in this repository. Fetch them with
``python tests/real_samples/fetch_samples.py``; without them these tests skip.
Optional live re-fetch of the whole pipeline: ``EASA_ERULES_LIVE=1``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from conftest import require_sample, sample_manifests, sample_path

from easa_erules.input.package import OpcPackage
from easa_erules.parser import EasaDocumentParser
from easa_erules.render import render_html, render_json, render_markdown
from easa_erules.validation import validate_document

REAL_DIR = Path("tests/real_samples")
LIVE = os.environ.get("EASA_ERULES_LIVE", "").strip() in {"1", "true", "yes"}


@pytest.mark.real_sample
@pytest.mark.parametrize(
    "manifest",
    sample_manifests(),
    ids=lambda p: p.name.split(".")[0] if isinstance(p, Path) else str(p),
)
def test_real_sample_parse_validate_convert(manifest: Path):
    """parse → validate → markdown/json/html smoke on real EAR XML."""
    path = require_sample(sample_path(manifest))
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


def test_sample_pins_are_complete():
    """Every pin carries what fetch_samples.py needs to reproduce the file."""
    manifests = sample_manifests()
    assert manifests, "expected pinned sample manifests under tests/real_samples/"
    for manifest in manifests:
        meta = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        assert (meta.get("source") or {}).get("download_url"), manifest.name
        assert (meta.get("integrity") or {}).get("sha256"), manifest.name
        assert (meta.get("version") or {}).get("label"), manifest.name


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
