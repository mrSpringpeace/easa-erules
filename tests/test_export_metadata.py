"""Tests for erules-export customXml + core properties metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from easa_erules.input.package import OpcPackage
from easa_erules.parser import EasaDocumentParser

REAL_VLA = Path("tests/real_samples/cs-vla.xml")
REAL_CS23 = Path("tests/real_samples/cs-23.xml")


@pytest.mark.skipif(not REAL_VLA.is_file(), reason="cs-vla real sample missing")
def test_cs_vla_export_metadata_and_designations():
    result = EasaDocumentParser(OpcPackage.from_file(REAL_VLA)).parse()
    doc = result.document

    assert doc.title and "CS-VLA" in doc.title
    easa = doc.easa_metadata or {}
    assert easa.get("source_title")
    assert easa.get("guid")
    assert easa.get("pub_time")
    assert (doc.metadata or {}).get("core_properties", {}).get("title")

    # Index requirements by designation
    by_des: dict[str, object] = {}

    def walk(n):
        des = getattr(n, "designation", "") or ""
        if des and hasattr(n, "erules_id"):
            by_des[des] = n
        for c in getattr(n, "children", []) or []:
            walk(c)

    walk(doc)

    assert "CS-VLA.1" in by_des
    req = by_des["CS-VLA.1"]
    assert req.erules_id.startswith("ERULES-")
    meta = (req.metadata or {}).get("easa") or {}
    assert meta.get("type_of_content")
    assert meta.get("sdt_id")
    assert meta.get("regulatory_source")

    assert "AMC VLA 1" in by_des
    amc = by_des["AMC VLA 1"]
    amc_meta = (amc.metadata or {}).get("easa") or {}
    assert any("AMC" in str(t) for t in (amc_meta.get("type_of_content") or []))

    # Unique opaque erules ids → no duplicate noise for real rule topics
    ids = []
    def walk_ids(n):
        eid = getattr(n, "erules_id", None)
        if eid:
            ids.append(eid)
        for c in getattr(n, "children", []) or []:
            walk_ids(c)
    walk_ids(doc)
    assert len(ids) == len(set(ids))


@pytest.mark.skipif(not REAL_CS23.is_file(), reason="cs-23 real sample missing")
def test_cs_23_designations_amc_gm():
    result = EasaDocumentParser(OpcPackage.from_file(REAL_CS23)).parse()
    desigs: set[str] = set()

    def walk(n):
        des = getattr(n, "designation", "") or ""
        if des:
            desigs.add(des)
        for c in getattr(n, "children", []) or []:
            walk(c)

    walk(result.document)

    assert "CS-23.2000" in desigs
    assert "AMC1 CS-23.2000" in desigs
    assert "GM1 CS-23.2010" in desigs
    # Must not collapse all rules to bare CS-23
    numbered = sum(1 for d in desigs if d.startswith("CS-23."))
    assert numbered > 10
    assert "CS-23" not in desigs
