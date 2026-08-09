"""Tests for registry, landing-page resolver, downloader, and cache (M7)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pytest
import yaml

from easa_erules.sources.cache import default_cache_root, version_cache_dir
from easa_erules.sources.downloader import EasaDownloader, resolve_local_source
from easa_erules.sources.registry import (
    clear_registry_cache,
    get_source,
    list_sources,
    load_registry,
    resolve_source_id,
)
from easa_erules.sources.resolver import (
    EasaSourceResolver,
    _slugify_version,
    parse_landing_page_publications,
)

SAMPLE_LANDING_HTML = """
<html><body>
  <a href="/en/downloads/66874/en" class="matomo_download"
     type="application/pdf; length=100"
     title="Easy Access Rules CS-VLA (Amendment 1).pdf">
     Easy Access Rules for Very Light Aeroplanes (CS-VLA) (Amendment 1)
  </a>
  <a href="/en/downloads/136669/en" class="matomo_download"
     type="application/zip; length=200"
     title="easy_access_rules_for_very_light_aeroplanes_cs-vla_amdt_1.zip">
     Easy Access Rules for Very Light Aeroplanes (CS-VLA) (Amendment 1) (XML)
  </a>
  <a href="/en/downloads/66873/en" class="matomo_download"
     type="application/pdf; length=150"
     title="Easy Access Rules CS-VLA (Initial Issue).pdf">
     Easy Access Rules for Very Light Aeroplanes (CS-VLA) (Initial issue)
  </a>
  <a href="/en/downloads/999/en" class="matomo_download"
     type="application/zip; length=50"
     title="old.zip">
     Easy Access Rules for Very Light Aeroplanes (CS-VLA) (Initial issue) (XML)
  </a>
</body></html>
"""


def test_registry_loads_yaml():
    clear_registry_cache()
    reg = load_registry()
    assert "cs-vla" in reg
    assert reg["cs-vla"]["landing_page"].startswith("https://")
    assert resolve_source_id("vla") == "cs-vla"
    assert resolve_source_id("CS23") == "cs-23"
    src = get_source("csvla")
    assert src["id"] == "cs-vla"
    assert len(list_sources()) >= 10
    assert resolve_source_id("cs-25") == "cs-25"
    assert resolve_source_id("ETSO") == "cs-etso"


def test_parse_landing_page_publications():
    pubs = parse_landing_page_publications(
        SAMPLE_LANDING_HTML,
        base_url="https://www.easa.europa.eu/en/document-library/easy-access-rules/cs-vla",
    )
    assert len(pubs) >= 3
    xml_pubs = [p for p in pubs if p.format == "xml"]
    assert len(xml_pubs) >= 2
    assert all(p.download_url.startswith("https://www.easa.europa.eu/") for p in pubs)
    assert any("Amendment 1" in p.version_label for p in xml_pubs)


def test_select_latest_xml_prefers_highest_amendment():
    pubs = parse_landing_page_publications(
        SAMPLE_LANDING_HTML,
        base_url="https://www.easa.europa.eu/",
    )
    resolver = EasaSourceResolver(
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    )
    try:
        selected = resolver.select_publication(pubs, preferred_format="xml")
    finally:
        resolver.close()
    assert selected is not None
    assert selected.format == "xml"
    assert "Amendment 1" in selected.version_label


def test_select_version_pin():
    pubs = parse_landing_page_publications(
        SAMPLE_LANDING_HTML,
        base_url="https://www.easa.europa.eu/",
    )
    resolver = EasaSourceResolver(
        client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    )
    try:
        selected = resolver.select_publication(
            pubs, version="Initial issue", preferred_format="xml"
        )
    finally:
        resolver.close()
    assert selected is not None
    assert "initial" in selected.version_label.lower()


def test_slugify_version():
    assert _slugify_version("Amendment 1") == "amendment-1"
    assert "initial" in _slugify_version("Initial issue")


def _zip_with_xml(xml_text: str = '<?xml version="1.0"?><pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage"/>') -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("doc.xml", xml_text)
    return buf.getvalue()


def test_fetch_downloads_and_caches(tmp_path: Path):
    zip_bytes = _zip_with_xml(
        '<?xml version="1.0"?><pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">'
        "<pkg:part pkg:name=\"/word/document.xml\"><pkg:xmlData>"
        "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
        "<w:body><w:p><w:r><w:t>hi</w:t></w:r></w:p></w:body></w:document>"
        "</pkg:xmlData></pkg:part></pkg:package>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "landing" in url or "easy-access-rules" in url or url.endswith("/cs-vla"):
            return httpx.Response(200, text=SAMPLE_LANDING_HTML)
        if "/downloads/136669/" in url:
            return httpx.Response(
                200,
                content=zip_bytes,
                headers={"content-type": "application/zip"},
            )
        if "/downloads/999/" in url:
            return httpx.Response(
                200,
                content=_zip_with_xml("<?xml version='1.0'?><root/>"),
                headers={"content-type": "application/zip"},
            )
        return httpx.Response(404, text=f"not found: {url}")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, follow_redirects=True)

    # Point registry landing page at a URL our mock handles
    # get_source uses real landing pages; mock matches "easy-access-rules" in URL
    with EasaDownloader(cache_root=tmp_path, client=client) as dl:
        # Override resolve by monkeypatching resolver.discover via real resolve
        # Real get_source landing_page contains easy-access-rules — mock returns HTML
        result = dl.fetch("cs-vla")
        assert result.from_cache is False
        assert result.source_path.exists()
        assert result.meta_path.exists()
        assert result.sha256
        assert result.size > 0
        meta = yaml.safe_load(result.meta_path.read_text(encoding="utf-8"))
        assert meta["document"] == "cs-vla"
        assert meta["integrity"]["sha256"] == result.sha256
        assert meta["source"]["download_url"]

        # Second fetch hits cache
        result2 = dl.fetch("cs-vla")
        assert result2.from_cache is True
        assert result2.source_path == result.source_path

        # Force re-download
        result3 = dl.fetch("cs-vla", force=True)
        assert result3.from_cache is False


def test_resolve_local_source_path_and_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Existing file path
    f = tmp_path / "local.xml"
    f.write_text("<?xml version='1.0'?><root/>", encoding="utf-8")
    assert resolve_local_source(str(f)) == f.resolve()

    # Cached document id
    vdir = version_cache_dir("cs-vla", "amendment-1", tmp_path)
    vdir.mkdir(parents=True)
    src = vdir / "source.xml"
    src.write_text("<?xml version='1.0'?><root/>", encoding="utf-8")
    (tmp_path / "cs-vla" / "source.xml").write_text(src.read_text(), encoding="utf-8")
    (tmp_path / "cs-vla" / "latest").write_text("amendment-1\n", encoding="utf-8")

    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    # default_cache_root reads env
    assert default_cache_root() == tmp_path.resolve()
    path = resolve_local_source("cs-vla", cache_root=tmp_path)
    assert path.exists()


def test_resolve_missing_source_message(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="fetch"):
        resolve_local_source("cs-vla", cache_root=tmp_path, auto_fetch=False)
