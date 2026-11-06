"""EASA publication-history.xml: parser, catalog mapping, cache.

Fixture: tests/fixtures/publication-history-subset.xml, a subset of
https://www.easa.europa.eu/gcs/files/publication-history.xml retrieved
2026-11-06 (full file SHA-256 59db70e0…732eb, 296 entries in 25 domains).
Expected values below are read from that file, not computed by the code.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from easa_erules.sources import get_source, list_sources
from easa_erules.sources.history import (
    PUBLICATION_HISTORY_URL,
    PublicationHistoryFormatError,
    catalog_format_problem,
    entries_for_codes,
    fetch_publication_history,
    history_cache_dir,
    load_cached_publication_history,
    parse_publication_history,
)

FIXTURE = Path(__file__).parent / "fixtures" / "publication-history-subset.xml"


@pytest.fixture(scope="module")
def entries():
    return parse_publication_history(FIXTURE.read_bytes())


def _easa_sources() -> list[dict]:
    return [s for s in list_sources() if s.get("authority") == "EASA"]


# --- the fixture parses, and the facts in it are the ones we read by hand -------


def test_fixture_entry_count(entries):
    # 140 <file> elements kept by the subset script; counted here as lines that
    # are exactly "<file>", so the header comment's mention does not count.
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    assert len(entries) == sum(1 for line in lines if line.strip() == "<file>") == 140


def test_cs_vla_amendment_1_xml_generation(entries):
    vla = entries_for_codes(entries, ["FE9752"])
    assert [(e.generated_at, e.notes) for e in vla] == [
        ("2022-06-28T07:52:05Z", "Amendment 1"),
        ("2018-11-14T16:32:33Z", "Amendment 1"),
        ("2018-11-14T16:25:58Z", "Initial issue"),
    ]
    xmlzip = vla[0].link("xmlzip")
    assert xmlzip is not None
    # MD5 as published; matches `md5sum` of the downloaded ZIP (checked 2026-11-06).
    assert xmlzip.md5 == "0d94bccb82aab8989d410b79872322e9"
    assert xmlzip.url == (
        "https://www.easa.europa.eu/en/gcs/files/"
        "FE9752_2022-06-28_07.52.05_EAR-for-Very-Light-Aeroplanes-CS-VLA.zip"
    )
    assert vla[0].link("pdf") is None
    assert vla[0].domain == "Initial Airworthiness and Environmental Protection"


def test_names_are_whitespace_normalised(entries):
    """95CADA is published once with a no-break space in its name and once without."""
    names = {e.ear_name for e in entries if e.ear_code == "95CADA"}
    assert names == {"Easy Access Rules for Continuing Airworthiness (Regulation (EU) No 1321/2014)"}


def test_same_notes_on_several_generations_are_all_kept(entries):
    """One entry is one generation: CS-29 Amendment 10 exists as XML and as PDF."""
    amdt10 = [e for e in entries_for_codes(entries, ["7643C9"]) if e.notes == "Amendment 10"]
    assert [(e.generated_at, [link.link_type for link in e.links]) for e in amdt10] == [
        ("2022-12-20T13:42:48Z", ["pdf"]),
        ("2022-12-19T01:12:09Z", ["xmlzip"]),
    ]


def test_part_21_spans_two_codes_newest_first(entries):
    part21 = entries_for_codes(entries, ["450F3E", "313A4D"])
    assert len(part21) == 12
    assert part21[0].ear_code == "313A4D"
    assert part21[0].notes == "Revision from November 2025"
    assert part21[-1].notes == "Revision from December 2019"


# --- the catalog points into the history ---------------------------------------


def test_every_easa_catalog_entry_has_ear_codes():
    for source in _easa_sources():
        codes = source.get("ear_codes")
        assert isinstance(codes, list) and codes, source["id"]
        for code in codes:
            assert isinstance(code, str) and re.fullmatch(r"[0-9A-F]{6}", code), (source["id"], code)


def test_every_catalog_code_names_one_publication_in_the_history(entries):
    """A code that is missing, or that maps to a different EAR, fails here."""
    for source in _easa_sources():
        matched = entries_for_codes(entries, source["ear_codes"])
        assert matched, f"{source['id']}: no history entry for {source['ear_codes']}"
        title = source["title"].lower()
        for entry in matched:
            assert title in entry.ear_name.lower() or source["id"] == "part-21", (
                source["id"],
                entry.ear_name,
            )


def test_no_code_is_claimed_by_two_catalog_entries():
    seen: dict[str, str] = {}
    for source in _easa_sources():
        for code in source["ear_codes"]:
            assert code not in seen, f"{code} in both {seen[code]} and {source['id']}"
            seen[code] = source["id"]


# --- structural surprises fail loudly ------------------------------------------

_ONE_FILE = """<XML><Title>t</Title><Domain><Name>D</Name><file><id>1</id>
<fileName>{file_name}</fileName><earName>Easy Access Rules for X</earName>
<links><link type="xmlzip" md5="{md5}">/en/gcs/files/x.zip</link></links>
<date>{date}</date><notes>Amendment 1</notes></file></Domain></XML>"""

_GOOD = {
    "file_name": "ABC123_2026-01-02_03.04.05_EAR-for-X",
    "md5": "0" * 32,
    "date": "2026-01-02T03:04:05Z",
}


def test_minimal_document_parses():
    (entry,) = parse_publication_history(_ONE_FILE.format(**_GOOD).encode())
    assert entry.ear_code == "ABC123"
    assert entry.links[0].url == "https://www.easa.europa.eu/en/gcs/files/x.zip"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"file_name": "not-a-coded-name"}, "fileName does not match"),
        ({"md5": "xyz"}, "md5"),
        ({"md5": ""}, "md5"),
        ({"date": "2026-01-02"}, "date"),
    ],
)
def test_malformed_file_entries_raise(override, message):
    with pytest.raises(PublicationHistoryFormatError, match=message):
        parse_publication_history(_ONE_FILE.format(**{**_GOOD, **override}).encode())


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"<html><body>Maintenance</body></html>", "Root element"),
        (b"<XML><Title>t</Title></XML>", "No <Domain>"),
        (b"<XML><Domain><Name>D</Name></Domain></XML>", "no <file>"),
        (b"not xml at all", "Not well-formed"),
    ],
)
def test_malformed_documents_raise(body, message):
    with pytest.raises(PublicationHistoryFormatError, match=message):
        parse_publication_history(body)


def test_external_entities_are_not_resolved(tmp_path: Path):
    secret = tmp_path / "secret.txt"
    secret.write_text("LEAKED", encoding="utf-8")
    body = (
        f'<?xml version="1.0"?><!DOCTYPE XML [<!ENTITY x SYSTEM "{secret.as_uri()}">]>'
        + _ONE_FILE.format(**_GOOD).replace("Amendment 1", "&x;")
    ).encode()
    (entry,) = parse_publication_history(body)
    assert "LEAKED" not in entry.notes


# --- cache ---------------------------------------------------------------------


def _client(body: bytes, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == PUBLICATION_HISTORY_URL
        return httpx.Response(status, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_then_load_round_trip(tmp_path: Path):
    body = FIXTURE.read_bytes()
    fetched = fetch_publication_history(cache_root=tmp_path, client=_client(body))
    assert len(fetched.entries) == 140
    assert fetched.path.read_bytes() == body

    loaded = load_cached_publication_history(tmp_path)
    assert loaded is not None
    assert loaded.sha256 == fetched.sha256
    assert loaded.entries == fetched.entries


def test_load_without_fetch_is_none(tmp_path: Path):
    assert load_cached_publication_history(tmp_path) is None


def test_malformed_download_does_not_replace_the_cache(tmp_path: Path):
    fetch_publication_history(cache_root=tmp_path, client=_client(FIXTURE.read_bytes()))
    with pytest.raises(PublicationHistoryFormatError):
        fetch_publication_history(cache_root=tmp_path, client=_client(b"<html/>"))
    loaded = load_cached_publication_history(tmp_path)
    assert loaded is not None and len(loaded.entries) == 140


def test_http_error_is_raised(tmp_path: Path):
    with pytest.raises(httpx.HTTPStatusError):
        fetch_publication_history(cache_root=tmp_path, client=_client(b"", status=503))
    assert not history_cache_dir(tmp_path).exists()


def test_tampered_cache_is_refused(tmp_path: Path):
    fetched = fetch_publication_history(cache_root=tmp_path, client=_client(FIXTURE.read_bytes()))
    fetched.path.write_bytes(fetched.path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_cached_publication_history(tmp_path)


def test_catalog_format_agrees_with_the_history(entries):
    """Every catalog entry's xml_available / preferred_format matches the history.

    Fails when EASA starts or stops publishing XML for a catalogued EAR
    (CS-ETSO switched with Amendment 17, generated 2026-10-15), or publishes a
    new version as PDF only; refresh the fixture from the live file and fix the
    catalog entry it names. The rule is catalog_format_problem().
    """
    problems = {s["id"]: catalog_format_problem(s, entries) for s in _easa_sources()}
    assert {k: v for k, v in problems.items() if v} == {}


@pytest.mark.parametrize(
    ("override", "problem"),
    [
        # CS-ETSO as catalogued before 2026-11-06:
        ({"preferred_format": "pdf", "xml_available": False}, "catalog says PDF only, history lists XML"),
        ({"preferred_format": "pdf"}, "preferred_format 'pdf' on an XML entry"),
        ({"ear_codes": []}, "no ear_codes"),
        ({"ear_codes": ["000000"]}, "no history entry"),
    ],
)
def test_catalog_format_problems_are_named(entries, override, problem):
    source = {**get_source("cs-etso"), **override}
    message = catalog_format_problem(source, entries)
    assert message is not None and message.startswith(problem)


def test_pdf_only_newest_version_is_a_problem(entries):
    """A new amendment published as PDF only must not pass as "XML available"."""
    # CS-P (DF6049) has PDF generations only; claiming XML for it must fail.
    source = {"id": "x", "ear_codes": ["DF6049"], "preferred_format": "xml"}
    message = catalog_format_problem(source, entries)
    assert message is not None and "has no XML generation" in message
