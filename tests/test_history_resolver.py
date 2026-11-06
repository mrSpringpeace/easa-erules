"""Resolver, downloader and version API on top of publication-history.xml.

Fixture: tests/fixtures/publication-history-subset.xml (see test_history.py).
Expected labels, dates and MD5s below are read from that file.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import httpx
import pytest
import yaml

from easa_erules import api
from easa_erules.contract import Status, ToolError
from easa_erules.sources.downloader import (
    EasaDownloader,
    PublisherChecksumError,
    verify_publisher_md5,
)
from easa_erules.sources.history import (
    PUBLICATION_HISTORY_URL,
    entries_for_codes,
    parse_publication_history,
)
from easa_erules.sources.resolver import (
    EasaSourceResolver,
    Publication,
    ResolveResult,
    history_version_label,
    publications_from_history,
)

FIXTURE = Path(__file__).parent / "fixtures" / "publication-history-subset.xml"
LANDING_HTML = "<html><body><p>landing page</p></body></html>"


def _history_pubs(codes: list[str]) -> list[Publication]:
    entries = parse_publication_history(FIXTURE.read_bytes())
    return publications_from_history(entries_for_codes(entries, codes))


class _Server:
    """MockTransport handler that records which URLs were requested."""

    def __init__(self, history: httpx.Response, files: dict[str, bytes] | None = None):
        self.history = history
        self.files = files or {}
        self.requested: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requested.append(url)
        if url == PUBLICATION_HISTORY_URL:
            return self.history
        if url in self.files:
            return httpx.Response(200, content=self.files[url])
        return httpx.Response(200, text=LANDING_HTML)


def _resolver(server: _Server) -> EasaSourceResolver:
    return EasaSourceResolver(client=httpx.Client(transport=httpx.MockTransport(server)))


# --- labels --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("notes", "label"),
    [
        ("CS Amendment 6, AMC/GM Issue 5", "Amendment 6 / Issue 5"),
        ("CS Amendment 5, AMC/GM Issue 3", "Amendment 5 / Issue 3"),
        ("Amentment 2", "Amendment 2"),  # CS-25, typo as published
        ("Amendment 17", "Amendment 17"),
        ("Initial issue", "Initial issue"),
        ("Issue 2", "Issue 2"),
        ("Revision from November 2025", "Revision from November 2025"),
        ("", "unknown"),
    ],
)
def test_history_version_label(notes: str, label: str):
    assert history_version_label(notes) == label


def test_cs23_amendment_6_generations_get_distinct_slugs():
    xml = [p for p in _history_pubs(["5E178D"]) if p.format == "xml"]
    assert [(p.version_slug, p.generated_at) for p in xml] == [
        ("amendment-6-issue-5", "2026-05-13T19:03:46Z"),
        ("amendment-6-issue-4", "2023-12-04T11:06:02Z"),
        ("amendment-5-issue-3", "2023-06-15T15:24:49Z"),
    ]


# --- resolver ------------------------------------------------------------------


def test_resolve_uses_history_and_skips_landing_page():
    server = _Server(httpx.Response(200, content=FIXTURE.read_bytes()))
    with _resolver(server) as resolver:
        result = resolver.resolve("cs-vla")
    assert result.inventory == "publication_history"
    assert result.warnings == []
    assert server.requested == [PUBLICATION_HISTORY_URL]
    selected = result.selected
    assert selected is not None
    assert (selected.version_slug, selected.format) == ("amendment-1", "xml")
    assert selected.md5 == "0d94bccb82aab8989d410b79872322e9"
    assert selected.generated_at == "2022-06-28T07:52:05Z"


def test_latest_follows_generation_date_not_amendment_number():
    """CS-29 Amendment 10 XML (2022-12-19) is older than 11 and 12."""
    server = _Server(httpx.Response(200, content=FIXTURE.read_bytes()))
    with _resolver(server) as resolver:
        result = resolver.resolve("cs-29")
    assert result.selected is not None
    assert result.selected.version_slug == "amendment-12"


@pytest.mark.parametrize(
    ("doc_id", "version", "slug"),
    [
        ("cs-23", "amendment-6-issue-4", "amendment-6-issue-4"),
        ("cs-23", "Amendment 6 / Issue 5", "amendment-6-issue-5"),
        ("part-21", "Revision from March 2023", "revision-from-march-2023"),
        ("cs-27", "Amendment 9", "amendment-9"),
    ],
)
def test_version_pin(doc_id: str, version: str, slug: str):
    server = _Server(httpx.Response(200, content=FIXTURE.read_bytes()))
    with _resolver(server) as resolver:
        result = resolver.resolve(doc_id, version=version)
    assert result.selected is not None
    assert result.selected.version_slug == slug


def test_pin_matching_two_versions_is_ambiguous_not_guessed():
    server = _Server(httpx.Response(200, content=FIXTURE.read_bytes()))
    with _resolver(server) as resolver, pytest.raises(LookupError, match="ambiguous") as excinfo:
        resolver.resolve("cs-23", version="Amendment 6")
    assert "amendment-6-issue-4" in str(excinfo.value)
    assert "amendment-6-issue-5" in str(excinfo.value)


def test_amendment_1_does_not_match_amendment_10():
    """CS-29 has XML for Amendments 10-12 only; "Amendment 1" is not one of them."""
    server = _Server(httpx.Response(200, content=FIXTURE.read_bytes()))
    with _resolver(server) as resolver, pytest.raises(LookupError, match="No publication matching"):
        resolver.resolve("cs-29", version="Amendment 1")


@pytest.mark.parametrize(
    ("history", "warning"),
    [
        (httpx.Response(503), "publication_history_unavailable"),
        (httpx.Response(200, text="<html>maintenance</html>"), "publication_history_unavailable"),
        (
            httpx.Response(200, content=b"<XML><Domain><Name>D</Name><file><fileName>AAAAAA_2026-01-01_00.00.00_x</fileName>"
            b"<earName>x</earName><links><link type='pdf' md5='" + b"0" * 32 + b"'>/x.pdf</link></links>"
            b"<date>2026-01-01T00:00:00Z</date><notes>n</notes></file></Domain></XML>"),
            "publication_history_has_no_entries",
        ),
    ],
)
def test_history_problems_fall_back_to_landing_page_loudly(history: httpx.Response, warning: str):
    server = _Server(history)
    with _resolver(server) as resolver:
        result = resolver.resolve("cs-vla")
    assert server.requested[0] == PUBLICATION_HISTORY_URL
    assert len(server.requested) == 2  # history, then the landing page
    assert result.inventory == "landing_page"
    assert len(result.warnings) == 1 and result.warnings[0].startswith(warning)
    # The landing-page stub has no downloads: nothing selected, nothing invented.
    assert result.publications == [] and result.selected is None


# --- downloader ----------------------------------------------------------------


def _zip(xml: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("doc.xml", xml)
    return buffer.getvalue()


_XML = b'<?xml version="1.0"?><pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage"/>'


def _pub(md5: str | None) -> Publication:
    return Publication(
        title="Very Light Aeroplanes (Amendment 1)",
        version_label="Amendment 1",
        version_slug="amendment-1",
        format="xml",
        download_url="https://www.easa.europa.eu/en/gcs/files/FE9752_x.zip",
        filename="FE9752_x.zip",
        md5=md5,
        generated_at="2022-06-28T07:52:05Z",
        history_file_name="FE9752_x",
        notes="Amendment 1",
    )


def test_verify_publisher_md5():
    data = b"abc"
    # RFC 1321, appendix A.5: MD5("abc") = 900150983cd24fb0d6963f7d28e17f72
    assert verify_publisher_md5(data, _pub("900150983cd24fb0d6963f7d28e17f72")) is True
    assert verify_publisher_md5(data, _pub(None)) is False
    with pytest.raises(PublisherChecksumError):
        verify_publisher_md5(data, _pub("0" * 32))


def _downloader(tmp_path: Path, pub: Publication, body: bytes) -> EasaDownloader:
    server = _Server(httpx.Response(404), files={pub.download_url: body})
    downloader = EasaDownloader(
        cache_root=tmp_path, client=httpx.Client(transport=httpx.MockTransport(server))
    )

    def resolve(doc_id: str, **_: object) -> ResolveResult:
        return ResolveResult(
            "cs-vla", "Very Light Aeroplanes", "https://landing", [pub], pub,
            inventory="publication_history",
        )

    downloader.resolver.resolve = resolve  # type: ignore[method-assign]
    return downloader


def test_fetch_records_history_provenance(tmp_path: Path):
    body = _zip(_XML)
    pub = _pub(hashlib.md5(body).hexdigest())
    with _downloader(tmp_path, pub, body) as downloader:
        result = downloader.fetch("cs-vla")
    meta = yaml.safe_load(result.meta_path.read_text(encoding="utf-8"))
    assert meta["source"]["inventory"] == "publication_history"
    assert meta["source"]["publisher_md5"] == pub.md5
    assert meta["source"]["publisher_md5_verified"] is True
    assert meta["source"]["generated_at"] == "2022-06-28T07:52:05Z"
    assert meta["source"]["history_file_name"] == "FE9752_x"
    assert result.source_path.read_bytes() == _XML


def test_fetch_with_wrong_md5_writes_nothing(tmp_path: Path):
    body = _zip(_XML)
    with _downloader(tmp_path, _pub("0" * 32), body) as downloader:
        with pytest.raises(PublisherChecksumError):
            downloader.fetch("cs-vla")
    assert not (tmp_path / "cs-vla").exists()


def test_api_maps_md5_mismatch_to_integrity_error(monkeypatch: pytest.MonkeyPatch):
    class Failing:
        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def fetch(self, *args: object, **kwargs: object):
            raise PublisherChecksumError("md5 differs")

    monkeypatch.setattr("easa_erules.sources.EasaDownloader", Failing)
    with pytest.raises(ToolError) as excinfo:
        api.fetch_regulation("cs-vla")
    assert excinfo.value.status is Status.INTEGRITY_ERROR


# --- version API -----------------------------------------------------------------


class _FakeResolver:
    def __init__(self, pubs: list[Publication]):
        self.pubs = pubs

    def __call__(self) -> _FakeResolver:
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        pass

    def resolve(self, doc_id: str, preferred_format: str) -> ResolveResult:
        return ResolveResult(
            doc_id, "t", "https://landing", self.pubs, None, inventory="publication_history"
        )


def test_remote_versions_from_history(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "easa_erules.sources.resolver.EasaSourceResolver", _FakeResolver(_history_pubs(["5E178D"]))
    )
    payload = api.list_remote_versions("cs-23")
    assert payload["inventory"] == "publication_history"
    rows = payload["versions"]
    assert [row["version_slug"] for row in rows] == [
        "amendment-6-issue-5",
        "amendment-6-issue-4",
        "amendment-5-issue-3",
    ]
    assert rows[0]["is_latest"] is True
    assert rows[0]["publisher_md5"] and rows[0]["generated_at"] == "2026-05-13T19:03:46Z"
    assert all(row["generations"] == 1 for row in rows)


def test_remote_versions_count_regenerations(monkeypatch: pytest.MonkeyPatch):
    older = _pub("1" * 32)
    newer = Publication(**{**older.to_dict(), "md5": "2" * 32, "generated_at": "2023-01-01T00:00:00Z"})
    monkeypatch.setattr(
        "easa_erules.sources.resolver.EasaSourceResolver", _FakeResolver([older, newer])
    )
    (row,) = api.list_remote_versions("cs-vla")["versions"]
    assert row["generations"] == 2
    assert row["publisher_md5"] == "2" * 32


def _cached(root: Path, slug: str, original_zip: bytes, inventory: str | None) -> None:
    directory = root / "cs-23" / "versions" / slug
    directory.mkdir(parents=True)
    xml = b"<xml/>"
    (directory / "source.xml").write_bytes(xml)
    (directory / "original.zip").write_bytes(original_zip)
    source = {"format": "xml", "download_url": "https://www.easa.europa.eu/en/downloads/143631/en"}
    if inventory:
        source["inventory"] = inventory
    if inventory == "publication_history":
        # What the downloader records: the MD5 the download was verified against.
        source["publisher_md5"] = hashlib.md5(original_zip).hexdigest()
    (directory / "meta.yaml").write_text(
        yaml.safe_dump(
            {
                "document": "cs-23",
                "version": {"label": "Amendment 6", "slug": slug},
                "retrieved_at": "2026-08-11T10:00:00Z",
                "integrity": {"sha256": hashlib.sha256(xml).hexdigest(), "size": len(xml)},
                "source": source,
            }
        ),
        encoding="utf-8",
    )


def _remote(rows: list[tuple[str, str, bool]]):
    return lambda doc_id: {
        "versions": [
            {
                "version_slug": slug,
                "is_latest": latest,
                "download_url": f"https://www.easa.europa.eu/en/gcs/files/{slug}.zip",
                "format": "xml",
                "reported_size": None,
                "inventory": "publication_history",
                "publisher_md5": md5,
            }
            for slug, md5, latest in rows
        ]
    }


def test_pre_history_cache_is_matched_by_publisher_md5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A CS-23 copy cached as "amendment-6" via the landing page is Issue 5."""
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    original = b"zip bytes of issue 5"
    _cached(tmp_path, "amendment-6", original, inventory=None)
    md5 = hashlib.md5(original).hexdigest()
    monkeypatch.setattr(
        api,
        "list_remote_versions",
        _remote([("amendment-6-issue-5", md5, True), ("amendment-6-issue-4", "4" * 32, False)]),
    )
    freshness = api.check_regulation_version("cs-23", "amendment-6")["freshness"]
    assert freshness["matched_by"] == "publisher_md5"
    assert freshness["remote_version_slug"] == "amendment-6-issue-5"
    assert freshness["state"] == "current"


def test_regenerated_version_is_remote_changed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    _cached(tmp_path, "amendment-6-issue-5", b"old generation", inventory="publication_history")
    monkeypatch.setattr(api, "list_remote_versions", _remote([("amendment-6-issue-5", "5" * 32, True)]))
    freshness = api.check_regulation_version("cs-23", "amendment-6-issue-5")["freshness"]
    assert freshness["matched_by"] == "version_slug"
    assert freshness["state"] == "remote_changed"


def test_inventories_without_md5_are_not_compared_by_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Landing-page URL vs history URL differ by construction; that is not a change,
    and not evidence of sameness either."""
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    _cached(tmp_path, "amendment-6", b"zip", inventory=None)
    (tmp_path / "cs-23" / "versions" / "amendment-6" / "original.zip").unlink()
    remote = _remote([("amendment-6", "", True)])
    monkeypatch.setattr(api, "list_remote_versions", remote)
    payload = api.check_regulation_version("cs-23", "amendment-6")
    assert payload["freshness"]["state"] == "unknown"
    assert any(w.startswith("shallow_check_not_comparable") for w in payload["warnings"])


def test_repackaged_landing_page_zip_is_unknown_not_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """CS-23 Amdt 5 (2026-11-06): the landing-page ZIP and the history ZIP have
    different MD5s but byte-identical XML. A shallow check cannot tell."""
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    _cached(tmp_path, "amendment-5", b"landing page packaging", inventory=None)
    monkeypatch.setattr(
        api,
        "list_remote_versions",
        _remote([("amendment-6-issue-5", "6" * 32, True), ("amendment-5-issue-3", "5" * 32, False)]),
    )
    payload = api.check_regulation_version("cs-23", "amendment-5")
    freshness = payload["freshness"]
    assert freshness["matched_by"] == "version_slug_prefix"
    assert freshness["remote_version_slug"] == "amendment-5-issue-3"
    # A newer version exists regardless of whether this one changed.
    assert freshness["state"] == "update_available"
    assert any(w.startswith("shallow_check_not_comparable") for w in payload["warnings"])


def test_ambiguous_slug_prefix_is_not_matched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    _cached(tmp_path, "amendment-6", b"unknown packaging", inventory=None)
    monkeypatch.setattr(
        api,
        "list_remote_versions",
        _remote([("amendment-6-issue-5", "6" * 32, True), ("amendment-6-issue-4", "4" * 32, False)]),
    )
    freshness = api.check_regulation_version("cs-23", "amendment-6")["freshness"]
    assert freshness["state"] == "remote_version_missing"
    assert freshness["matched_by"] is None


# --- landing page vs history (scripts/catalog_health.py) ------------------------
# Landing-page values below are what the live pages served on 2026-11-06.


def _landing(label: str, filename: str) -> Publication:
    from easa_erules.sources.resolver import _slugify_version

    slug = _slugify_version(label) if label != "unknown" else "unknown"
    return Publication("t", label, slug, "xml", "https://www.easa.europa.eu/en/downloads/1/en", filename=filename)


def _newest_xml(codes: list[str]) -> Publication:
    return next(p for p in _history_pubs(codes) if p.format == "xml")


@pytest.mark.parametrize(
    ("codes", "label", "filename"),
    [
        (["FE9752"], "Amendment 1", "easy_access_rules_for_very_light_aeroplanes_cs-vla_amdt_1.zip"),
        (["5E178D"], "Amendment 6", "5e178d_2026-05-13_19.03.46_ear-for-normal-category-aeroplanes-cs-23.zip"),
        (
            ["450F3E", "313A4D"],
            "unknown",
            "313A4D_2025-11-27_11.38.35_EAR-for-Initial-Airworthiness-and-Environmental-Protection-Regulation-EU-No-748-2012.zip",
        ),
    ],
)
def test_landing_page_agrees_on_live_examples(codes, label, filename):
    from easa_erules.sources.resolver import landing_page_agrees

    assert landing_page_agrees(_landing(label, filename), _newest_xml(codes))


@pytest.mark.parametrize(
    ("codes", "label", "filename"),
    [
        # Landing page still on Amendment 11 while the history has 12:
        (["7643C9"], "Amendment 11", "easy_access_rules_for_cs-29_amdt_11.zip"),
        # "Amendment 1" must not pass for "Amendment 12":
        (["7643C9"], "Amendment 1", "x.zip"),
        # No label and a file name the history does not know: cannot agree.
        (["D0593E"], "unknown", "something_else.zip"),
    ],
)
def test_landing_page_disagreement_is_detected(codes, label, filename):
    from easa_erules.sources.resolver import landing_page_agrees

    assert not landing_page_agrees(_landing(label, filename), _newest_xml(codes))
