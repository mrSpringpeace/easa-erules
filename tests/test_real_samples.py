"""Smoke tests for real EASA publications (optional).

Enable by placing XML/DOCX files under tests/real_samples/ or by setting
EASA_ERULES_LIVE=1 (will use cache / fetch if network available).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from easa_erules.input.package import OpcPackage
from easa_erules.parser import EasaDocumentParser
from easa_erules.render import render_json, render_markdown
from easa_erules.validation import validate_document

REAL_DIR = Path("tests/real_samples")
LIVE = os.environ.get("EASA_ERULES_LIVE", "").strip() in {"1", "true", "yes"}


def _local_real_files() -> list[Path]:
    if not REAL_DIR.is_dir():
        return []
    files: list[Path] = []
    for pattern in ("*.xml", "*.docx"):
        files.extend(REAL_DIR.glob(pattern))
    return sorted(files)


def test_real_samples_directory_documented():
    """Placeholder when no real samples are checked in."""
    files = _local_real_files()
    if not files:
        pytest.skip(
            "No files in tests/real_samples/ — add CS-VLA/CS-23 XML dumps for smoke tests"
        )
    for path in files:
        result = EasaDocumentParser(OpcPackage.from_file(path)).parse()
        assert result.document is not None
        report = validate_document(
            result.document,
            result.assets,
            result.references,
            parse_warnings=result.warnings,
            unknown_elements=result.unknown_elements,
            source_topic_count=result.source_topic_count,
        )
        assert report.topics >= 1 or report.paragraphs >= 1
        assert render_markdown(result.document)
        assert "document" in render_json(result.document, result.assets, result.references)


@pytest.mark.skipif(not LIVE, reason="Set EASA_ERULES_LIVE=1 for network fetch smoke")
def test_live_fetch_cs_vla_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Optional live fetch + parse of CS-VLA (network required)."""
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    from easa_erules.sources import EasaDownloader

    with EasaDownloader(cache_root=tmp_path) as dl:
        fetched = dl.fetch("cs-vla")
    assert fetched.source_path.exists()
    result = EasaDocumentParser(OpcPackage.from_file(fetched.source_path)).parse()
    assert result.source_topic_count > 10
    report = validate_document(
        result.document,
        result.assets,
        result.references,
        source_topic_count=result.source_topic_count,
    )
    assert report.topics > 10
