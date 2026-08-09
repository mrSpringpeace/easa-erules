"""Tests for SQLite FTS5 search index and query (M8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from easa_erules.input.package import OpcPackage
from easa_erules.parser import EasaDocumentParser
from easa_erules.search import ensure_index, prepare_fts_query, search
from easa_erules.search.indexer import build_index, sha256_file

FIXTURE = Path("tests/fixtures/cs-vla-sample.xml")


@pytest.fixture
def indexed(tmp_path: Path) -> Path:
    """Build a fresh index for the sample fixture under tmp_path."""
    db = tmp_path / "search.sqlite"
    pkg = OpcPackage.from_file(FIXTURE)
    result = EasaDocumentParser(pkg).parse()
    build_index(
        result,
        db_path=db,
        document_key="cs-vla",
        source_path=FIXTURE,
        source_sha256=sha256_file(FIXTURE),
    )
    return db


def test_prepare_fts_query_and_phrase():
    assert 'AND' in prepare_fts_query("factor of safety")
    assert '"factor of safety"' in prepare_fts_query('"factor of safety"')
    assert prepare_fts_query("   ") == ""


def test_index_and_search_factor_of_safety(indexed: Path):
    result = search(indexed, "factor of safety", document_key="cs-vla")
    assert result.total >= 1
    designations = {h.designation for h in result.hits}
    assert "CS-VLA.303" in designations
    hit = next(h for h in result.hits if h.designation == "CS-VLA.303")
    assert "factor" in hit.snippet.lower() or "factor" in hit.text_preview.lower()
    assert hit.topic_type == "requirement"


def test_search_strength_deformation(indexed: Path):
    result = search(indexed, "strength deformation", document_key="cs-vla")
    assert result.total >= 1
    assert any(h.designation == "CS-VLA.305" for h in result.hits)


def test_search_json_shape(indexed: Path):
    result = search(indexed, "factor", document_key="cs-vla", limit=5)
    data = result.to_dict()
    assert "document" in data
    assert data["query"] == "factor"
    assert "hits" in data
    assert isinstance(data["hits"], list)
    if data["hits"]:
        h = data["hits"][0]
        assert "designation" in h
        assert "snippet" in h
        assert "type" in h


def test_ensure_index_caches_and_invalidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    # First build
    db1 = ensure_index(FIXTURE, document_key="cs-vla", cache_root=tmp_path)
    assert db1.exists()
    mtime1 = db1.stat().st_mtime_ns

    # Second call should reuse (same sha + parser version)
    db2 = ensure_index(FIXTURE, document_key="cs-vla", cache_root=tmp_path)
    assert db2 == db1
    mtime2 = db2.stat().st_mtime_ns
    assert mtime2 == mtime1

    # Force rebuild
    db3 = ensure_index(FIXTURE, document_key="cs-vla", cache_root=tmp_path, force=True)
    assert db3.exists()
    assert db3.stat().st_mtime_ns >= mtime1

    # Parser version change invalidates
    import easa_erules.search.indexer as indexer_mod

    original = indexer_mod.__version__
    try:
        # Patch version used by ensure_index comparison
        import easa_erules as root_mod
        monkeypatch.setattr(root_mod, "__version__", "9.9.9-test")
        monkeypatch.setattr(indexer_mod, "__version__", "9.9.9-test")
        db4 = ensure_index(FIXTURE, document_key="cs-vla", cache_root=tmp_path)
        assert db4.exists()
    finally:
        monkeypatch.setattr(indexer_mod, "__version__", original)


def test_empty_query_returns_no_hits(indexed: Path):
    result = search(indexed, "   ", document_key="cs-vla")
    assert result.total == 0
    assert result.hits == []
