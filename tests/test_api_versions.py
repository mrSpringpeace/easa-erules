from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest
import yaml

from easa_erules import api
from easa_erules.sources.resolver import Publication, ResolveResult


def _cached_version(root: Path, slug: str, body: bytes = b"<xml/>") -> Path:
    directory = root / "cs-vla" / "versions" / slug
    directory.mkdir(parents=True)
    source = directory / "source.xml"
    source.write_bytes(body)
    (directory / "meta.yaml").write_text(
        yaml.safe_dump(
            {
                "document": "cs-vla",
                "version": {"label": slug.replace("-", " ").title(), "slug": slug},
                "retrieved_at": "2026-08-11T10:00:00Z",
                "integrity": {"sha256": hashlib.sha256(body).hexdigest(), "size": len(body)},
                "source": {"format": "xml", "download_url": "https://example.test/doc"},
            }
        ),
        encoding="utf-8",
    )
    return source


def test_list_cached_versions_is_local_and_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    _cached_version(tmp_path, "amendment-1")
    payload = api.list_cached_versions("cs-vla", verify_integrity=True)
    assert payload["status"] == "ok"
    assert payload["versions"][0]["version_slug"] == "amendment-1"
    assert payload["versions"][0]["integrity"]["state"] == "ok"


def test_remote_versions_are_newest_first(monkeypatch: pytest.MonkeyPatch):
    class FakeResolver:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def resolve(self, doc_id: str, preferred_format: str) -> ResolveResult:
            pubs = [
                Publication("old", "Amendment 1", "amendment-1", "xml", "https://e/1"),
                Publication("new", "Amendment 2", "amendment-2", "xml", "https://e/2"),
            ]
            return ResolveResult(doc_id, "VLA", "https://e/landing", pubs, pubs[-1])

    monkeypatch.setattr("easa_erules.sources.resolver.EasaSourceResolver", FakeResolver)
    payload = api.list_remote_versions("cs-vla")
    assert [item["version_slug"] for item in payload["versions"]] == [
        "amendment-2",
        "amendment-1",
    ]
    assert payload["versions"][0]["is_latest"] is True


def test_pdf_only_remote_inventory_is_successful_catalog_result():
    payload = api.list_remote_versions("cs-p")
    assert payload["status"] == "ok"
    assert payload["convertible"] is False
    assert payload["versions"] == []


def test_check_reports_update_available_without_overwriting_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    _cached_version(tmp_path, "amendment-1")
    monkeypatch.setattr(
        api,
        "list_remote_versions",
        lambda doc_id: {
            "versions": [
                {
                    "version_slug": "amendment-2",
                    "is_latest": True,
                    "download_url": "https://e/2",
                    "format": "xml",
                    "reported_size": None,
                },
                {
                    "version_slug": "amendment-1",
                    "is_latest": False,
                    "download_url": "https://example.test/doc",
                    "format": "xml",
                    "reported_size": None,
                },
            ]
        },
    )
    payload = api.check_regulation_version("cs-vla", "amendment-1")
    assert payload["freshness"]["state"] == "update_available"
    assert (tmp_path / "cs-vla" / "versions" / "amendment-1" / "source.xml").read_bytes() == b"<xml/>"


def test_deep_check_hashes_extracted_xml_not_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    source = _cached_version(tmp_path, "amendment-1")
    publication = Publication(
        "same",
        "Amendment 1",
        "amendment-1",
        "xml",
        "https://example.test/doc",
        filename="bundle.zip",
        content_type="application/zip",
    )

    monkeypatch.setattr(
        api,
        "list_remote_versions",
        lambda doc_id: {
            "versions": [
                {
                    "version_slug": "amendment-1",
                    "is_latest": True,
                    "download_url": publication.download_url,
                    "format": "xml",
                    "reported_size": None,
                }
            ]
        },
    )

    class FakeDownloader:
        resolver: object

        def __init__(self):
            self.resolver = self

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def resolve(self, doc_id: str, preferred_format: str) -> ResolveResult:
            return ResolveResult(doc_id, "VLA", "https://e", [publication], publication)

        def _download_bytes(self, url: str) -> bytes:
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr("document.xml", source.read_bytes())
            return buffer.getvalue()

    monkeypatch.setattr("easa_erules.sources.downloader.EasaDownloader", FakeDownloader)
    payload = api.check_regulation_version("cs-vla", "amendment-1", deep=True)
    assert payload["freshness"]["state"] == "current"
    assert payload["freshness"]["deep_verified"] is True


def test_same_version_changed_url_is_remote_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    _cached_version(tmp_path, "amendment-1")
    monkeypatch.setattr(
        api,
        "list_remote_versions",
        lambda doc_id: {
            "versions": [
                {
                    "version_slug": "amendment-1",
                    "is_latest": True,
                    "download_url": "https://changed.test/doc",
                    "format": "xml",
                    "reported_size": None,
                }
            ]
        },
    )
    payload = api.check_regulation_version("cs-vla", "amendment-1")
    assert payload["freshness"]["state"] == "remote_changed"
