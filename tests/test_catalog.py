"""Catalog integrity: formats are honoured, PDF-only entries fail clearly."""

from __future__ import annotations

import pytest

from easa_erules import api
from easa_erules.contract import Status, ToolError
from easa_erules.sources import get_source, list_sources
from easa_erules.sources.resolver import EasaSourceResolver, Publication


def _pub(fmt: str, label: str = "Amendment 1") -> Publication:
    return Publication(
        title=f"Test ({label}) ({fmt.upper()})",
        version_label=label,
        version_slug=label.lower().replace(" ", "-"),
        format=fmt,
        download_url=f"https://example.invalid/{fmt}",
    )


def test_no_silent_fallback_to_another_format():
    """CS-ETSO is PDF-only; selecting the PDF as 'the XML' fails a layer down."""
    resolver = EasaSourceResolver.__new__(EasaSourceResolver)
    with pytest.raises(LookupError, match="No 'xml' publication"):
        resolver.select_publication([_pub("pdf"), _pub("other")], preferred_format="xml")


def test_preferred_format_is_honoured_when_present():
    resolver = EasaSourceResolver.__new__(EasaSourceResolver)
    chosen = resolver.select_publication(
        [_pub("pdf"), _pub("xml")], preferred_format="xml"
    )
    assert chosen is not None
    assert chosen.format == "xml"


def test_unknown_version_is_reported_not_substituted():
    resolver = EasaSourceResolver.__new__(EasaSourceResolver)
    with pytest.raises(LookupError, match="No publication matching version"):
        resolver.select_publication(
            [_pub("xml", "Amendment 1")], version="Amendment 99", preferred_format="xml"
        )


@pytest.mark.parametrize("doc_id", ["cs-p", "cs-etso"])
def test_pdf_only_entries_are_flagged_in_the_catalog(doc_id: str):
    entry = get_source(doc_id)
    assert entry["xml_available"] is False
    assert entry["preferred_format"] == "pdf"


@pytest.mark.parametrize("doc_id", ["cs-p", "cs-etso"])
def test_pdf_only_entries_fail_with_an_explanation(doc_id: str):
    """Not a parse error somewhere deep in the OOXML reader."""
    with pytest.raises(ToolError) as excinfo:
        api.extract_rule(doc_id, "anything")
    assert excinfo.value.status is Status.ERROR
    assert "PDF only" in excinfo.value.message
    assert "landing" in excinfo.value.message or "easa.europa.eu" in excinfo.value.message


def test_every_catalog_entry_is_well_formed():
    for entry in list_sources():
        assert entry["title"], entry["id"]
        assert entry["authority"] in {"EASA", "FAA"}, entry["id"]
        assert entry["preferred_format"] in {"xml", "pdf"}, entry["id"]
        if entry["authority"] == "EASA":
            assert entry["landing_page"].startswith("https://"), entry["id"]
        else:
            assert entry["ecfr"]["part"], entry["id"]


def test_catalogs_share_one_id_space():
    ids = [e["id"] for e in list_sources()]
    assert len(ids) == len(set(ids))
    assert {"cs-vla", "far-23"} <= set(ids)
