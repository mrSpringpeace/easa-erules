"""FAA eCFR adapter — same AST, same contract, different authority."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from easa_erules import api
from easa_erules.adapters import get_adapter
from easa_erules.adapters.faa import FaaEcfrAdapter
from easa_erules.model import ParagraphNode, RegulationRequirement, RegulationSection
from easa_erules.parsing import is_ecfr_xml, parse_any

LIVE = os.environ.get("EASA_ERULES_LIVE", "").strip() in {"1", "true", "yes"}

ECFR_SAMPLE = """<?xml version="1.0"?>
<DIV6 N="A" TYPE="SUBPART" hierarchy_metadata="{&amp;quot;citation&amp;quot;:&amp;quot;14 CFR Part 23 Subpart A&amp;quot;}">
<HEAD>Subpart A&#x2014;General</HEAD>
<DIV8 N="23.2000" TYPE="SECTION" hierarchy_metadata="{&quot;citation&quot;:&quot;14 CFR 23.2000&quot;}">
<HEAD>&#xA7; 23.2000 Applicability and definitions.</HEAD>
<P>(a) This part prescribes airworthiness standards for normal category airplanes.</P>
<P><I>Continued safe flight and landing</I> means controlled flight and landing.</P>
</DIV8>
<DIV8 N="23.2005" TYPE="SECTION" hierarchy_metadata="{&quot;citation&quot;:&quot;14 CFR 23.2005&quot;}">
<HEAD>&#xA7; 23.2005 Certification of normal category airplanes.</HEAD>
<P>(a) Certification in the normal category applies to airplanes.</P>
</DIV8>
</DIV6>
"""


@pytest.fixture
def ecfr_file(tmp_path: Path) -> Path:
    path = tmp_path / "far-23.xml"
    path.write_text(ECFR_SAMPLE, encoding="utf-8")
    return path


def test_adapter_registry_returns_ecfr_adapter():
    adapter = get_adapter("faa")
    assert isinstance(adapter, FaaEcfrAdapter)
    caps = adapter.capabilities()
    assert caps.fetch and caps.parse and caps.search


def test_astm_adapter_is_gone():
    """ASTM is paywalled and cannot be redistributed — no adapter should pretend."""
    with pytest.raises(ValueError, match="Unknown authority"):
        get_adapter("astm")


def test_faa_sources_are_in_the_shared_catalog():
    ids = {s["id"] for s in get_adapter("faa").list_sources()}
    assert {"far-21", "far-23", "far-25"} <= ids

    from easa_erules.sources import get_source

    assert get_source("far23")["authority"] == "FAA"
    assert get_source("cs-vla")["authority"] == "EASA"


def test_sniffer_distinguishes_ecfr_from_ooxml(ecfr_file: Path):
    assert is_ecfr_xml(ecfr_file)
    assert not is_ecfr_xml(Path("tests/fixtures/cs-vla-sample.xml"))


def test_parses_into_the_shared_ast(ecfr_file: Path):
    result = parse_any(ecfr_file)
    doc = result.document

    assert doc.authority == "FAA"
    assert result.source_topic_count == 2

    subparts = [c for c in doc.children if isinstance(c, RegulationSection)]
    assert len(subparts) == 1
    assert subparts[0].title == "Subpart A—General"

    rules = [c for c in subparts[0].children if isinstance(c, RegulationRequirement)]
    assert [r.designation for r in rules] == ["14 CFR 23.2000", "14 CFR 23.2005"]
    assert rules[0].title == "Applicability and definitions"

    paragraphs = [c for c in rules[0].children if isinstance(c, ParagraphNode)]
    assert len(paragraphs) == 2
    assert paragraphs[0].get_text().startswith("(a) This part prescribes")
    assert "Continued safe flight" in paragraphs[1].get_text()


def test_extract_works_through_the_normal_api(ecfr_file: Path):
    payload = api.extract_rule(str(ecfr_file), "14 CFR 23.2005")
    assert payload["status"] == "ok"
    assert payload["rule"]["rule"] == "14 CFR 23.2005"
    assert payload["source"]["sha256"]


def test_designation_normalization():
    adapter = FaaEcfrAdapter()
    assert adapter.normalize_designation("§ 23.2000") == "14 CFR 23.2000"
    assert adapter.normalize_designation("FAR 23.2005") == "14 CFR 23.2005"
    assert adapter.normalize_designation("14 CFR 23.2010") == "14 CFR 23.2010"
    assert adapter.normalize_designation("") == ""


def test_fetch_rejects_a_non_date_version():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        FaaEcfrAdapter().fetch("far-23", version="Amendment 1")


@pytest.mark.skipif(not LIVE, reason="Set EASA_ERULES_LIVE=1 for the eCFR network smoke")
def test_live_ecfr_fetch_and_query(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    payload = api.fetch_regulation("far-23")
    assert payload["status"] == "ok"

    hits = api.query_regulation("far-23", "stall speed", limit=3)
    assert hits["status"] == "ok"
    assert hits["hits"]
    assert all(h["designation"].startswith("14 CFR 23.") for h in hits["hits"])
