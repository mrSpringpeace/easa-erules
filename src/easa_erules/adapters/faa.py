"""FAA adapter — 14 CFR via the public eCFR API.

This is the cheap branch. 14 CFR is US Government work in the public domain and
eCFR serves it as structured XML, so there is no OOXML unpacking, no Word SDT
guesswork and none of the redistribution care the EASA branch needs.

The mapping onto the shared Regulation AST is deliberately literal:

* ``DIV5``  PART     → :class:`RegulationDocument`
* ``DIV6``  SUBPART  → :class:`RegulationSection`
* ``DIV7``  SUBJGRP  → :class:`RegulationSection`
* ``DIV8``  SECTION  → :class:`RegulationRequirement` (designation ``14 CFR 23.2000``)
* ``P``              → :class:`ParagraphNode`

Because the output is the same AST, ``extract`` / ``query`` / ``refs`` work
against FAA parts with no further changes.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from lxml import etree

from .. import __version__
from ..model import (
    AssetCollection,
    BoldNode,
    ItalicNode,
    ParagraphNode,
    ReferenceIndex,
    RegulationDocument,
    RegulationRequirement,
    RegulationSection,
    TextNode,
)
from ..parser.document import ParseResult
from ..sources.cache import document_cache_dir, version_cache_dir
from .base import AdapterCapabilities, RegulationAdapter

ECFR_API = "https://www.ecfr.gov/api/versioner/v1"
USER_AGENT = f"easa-erules/{__version__} (+https://github.com/mrSpringpeace/easa-erules)"

#: ``§ 23.2000 Applicability and definitions.``
_HEAD_RE = re.compile(r"^\s*§+\s*(?P<number>[\d.]+[A-Za-z]?)\s*(?P<title>.*?)\.?\s*$")


def _text_of(elem: etree._Element) -> str:
    return "".join(elem.itertext())


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


class FaaEcfrAdapter(RegulationAdapter):
    """Fetch and parse 14 CFR parts from eCFR into the shared AST."""

    authority = "faa"

    def __init__(self) -> None:
        self._warnings: list[dict[str, Any]] = []
        self._unknown: list[dict[str, Any]] = []

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            authority=self.authority,
            fetch=True,
            parse=True,
            search=True,
            designations=True,
            notes=(
                "Experimental. Parts fetched whole from the eCFR versioner API; "
                "the AST is the same one the EASA branch produces. EASA is the "
                "maintained branch — treat this output shape as unstable."
            ),
            planned=[
                "Advisory Circulars (no structured public API — needs a different route)",
                "Appendices and tables inside parts (currently flattened to paragraphs)",
                "Cross-reference detection tuned for FAR citation style",
            ],
        )

    # --- catalog -----------------------------------------------------------

    def list_sources(self) -> list[dict[str, Any]]:
        from ..sources.registry import list_sources as _list

        return [s for s in _list() if str(s.get("authority", "")).upper() == "FAA"]

    def _entry(self, source_id: str) -> dict[str, Any]:
        from ..sources.registry import get_source

        source = get_source(source_id)
        if str(source.get("authority", "")).upper() != "FAA":
            raise ValueError(f"{source_id} is not an FAA source")
        if not source.get("ecfr"):
            raise ValueError(f"{source_id} has no 'ecfr' catalog block")
        return source

    def download_url(self, source_id: str, *, on_date: str) -> str:
        entry = self._entry(source_id)
        ecfr = entry["ecfr"]
        return f"{ECFR_API}/full/{on_date}/title-{ecfr['title']}.xml?part={ecfr['part']}"

    def latest_issue_date(self, source_id: str) -> str:
        """Newest date eCFR actually holds for this title.

        Today's date is not a safe default: eCFR lags the calendar and returns
        404 for a date it has no issue for.
        """
        import httpx

        entry = self._entry(source_id)
        title = int(entry["ecfr"]["title"])
        with httpx.Client(
            follow_redirects=True, timeout=60.0, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = client.get(f"{ECFR_API}/titles.json")
            response.raise_for_status()
            titles = response.json().get("titles", [])
        for item in titles:
            if item.get("number") == title:
                issue = item.get("latest_issue_date") or item.get("up_to_date_as_of")
                if issue:
                    return str(issue)
        raise LookupError(f"eCFR reports no issue date for title {title}")

    # --- fetch -------------------------------------------------------------

    def fetch(
        self,
        source_id: str,
        *,
        version: str | None = None,
        cache_root: Path | None = None,
    ) -> Path:
        """Download a part as of *version* (ISO date; default: latest eCFR issue)."""
        import httpx

        entry = self._entry(source_id)
        on_date = version or self.latest_issue_date(source_id)
        try:
            datetime.strptime(on_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(
                f"FAA versions are eCFR dates in YYYY-MM-DD form, got {on_date!r}"
            ) from exc

        url = self.download_url(source_id, on_date=on_date)
        vdir = version_cache_dir(entry["id"], on_date, cache_root)
        vdir.mkdir(parents=True, exist_ok=True)
        source_path = vdir / "source.xml"

        with httpx.Client(
            follow_redirects=True, timeout=120.0, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            payload = response.content

        source_path.write_bytes(payload)
        meta = {
            "document": entry["id"],
            "title": entry["title"],
            "authority": "FAA",
            "version": {"label": f"eCFR as of {on_date}", "slug": on_date},
            "source": {
                "landing_page": f"https://www.ecfr.gov/current/title-{entry['ecfr']['title']}"
                f"/part-{entry['ecfr']['part']}",
                "download_url": url,
                "filename": f"{entry['id']}-{on_date}.xml",
                "format": "xml",
            },
            "retrieved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "integrity": {
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
            },
        }
        (vdir / "meta.yaml").write_text(
            yaml.dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

        # Convenience "latest" copy at the document root, as the EASA branch does
        doc_dir = document_cache_dir(entry["id"], cache_root)
        (doc_dir / "source.xml").write_bytes(payload)
        (doc_dir / "meta.yaml").write_text(
            (vdir / "meta.yaml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        (doc_dir / "latest").write_text(on_date + "\n", encoding="utf-8")
        return source_path

    # --- parse -------------------------------------------------------------

    def parse(self, path: str | Path) -> ParseResult:
        """Parse an eCFR part XML file into a :class:`ParseResult`."""
        root = etree.parse(str(path)).getroot()
        return self.parse_element(root)

    def parse_element(self, root: etree._Element) -> ParseResult:
        # Structure this adapter does not model yet is recorded, never dropped
        # in silence — the project's "no silent content loss" rule applies to
        # the experimental branch too.
        self._warnings: list[dict[str, Any]] = []
        self._unknown: list[dict[str, Any]] = []

        document = RegulationDocument()
        document.authority = "FAA"
        document.metadata = {}

        part_elem = root if root.tag == "DIV5" else root.find(".//DIV5")
        anchor = part_elem if part_elem is not None else root
        citation = self._citation(anchor)

        document.document_id = self._document_id(citation, anchor)
        document.title = _clean(self._head_text(anchor)) or document.document_id
        document.version = ""
        document.metadata["ecfr"] = {"citation": citation}

        section_count = 0
        if part_elem is None and anchor.tag in ("DIV6", "DIV7", "DIV8"):
            # Partial export (a single subpart or section): keep its own container
            section_count += self._dispatch(anchor, document)
        else:
            for child in anchor:
                section_count += self._dispatch(child, document)

        from ..util.ids import assign_deterministic_ids

        assign_deterministic_ids(document)

        from ..normalize import normalize_document

        normalize_document(document, authority="FAA")

        from ..parser.document import resolve_document_references

        resolve_document_references(document)

        return ParseResult(
            document=document,
            assets=AssetCollection(),
            references=ReferenceIndex(),
            warnings=self._warnings,
            unknown_elements=self._unknown,
            source_topic_count=section_count,
        )

    # --- internals ---------------------------------------------------------

    def _citation(self, elem: etree._Element) -> str:
        raw = elem.get("hierarchy_metadata") or ""
        match = re.search(r"citation&(?:amp;)?quot;:&(?:amp;)?quot;([^&]+)&", raw)
        return match.group(1) if match else ""

    def _head_text(self, elem: etree._Element) -> str:
        head = elem.find("HEAD")
        return _text_of(head) if head is not None else ""

    def _document_id(self, citation: str, elem: etree._Element) -> str:
        if citation:
            return citation.replace("§", "").strip()
        number = elem.get("N") or ""
        return f"14 CFR {number}".strip()

    def _dispatch(self, elem: etree._Element, parent: Any) -> int:
        """Attach *elem* under *parent*. Returns the number of sections found."""
        tag = elem.tag
        if tag == "HEAD":
            return 0
        if tag in ("DIV6", "DIV7"):
            # The container is a topic in its own right, like the sections it holds
            return 1 + self._parse_container(elem, parent)
        if tag == "DIV8":
            self._parse_section(elem, parent)
            return 1
        if tag.startswith(("P", "FP")):
            self._parse_paragraph(elem, parent)
            return 0
        if tag in ("TABLE", "GPOTABLE", "BOXTXT"):
            self._flatten_table(elem, parent)
            return 0
        if tag == "img":
            self._note_unsupported(elem, parent, "image not extracted")
            return 0

        # Anything unrecognised: keep its text rather than drop it
        found = 0
        for child in elem:
            found += self._dispatch(child, parent)
        if not len(elem):
            text = _clean(_text_of(elem))
            if text:
                self._add_paragraph(parent, text)
        return found

    def _section_of(self, parent: Any) -> str:
        """Nearest enclosing rule designation, for warning context."""
        node = parent
        while node is not None:
            designation = getattr(node, "designation", "")
            if designation:
                return str(designation)
            node = getattr(node, "parent", None)
        return ""

    def _flatten_table(self, elem: etree._Element, parent: Any) -> None:
        """Render a table as running text and say so.

        Tables are not modelled by this adapter yet. Turning one into a
        paragraph loses its structure, so the loss is reported rather than
        left for a reader to discover.
        """
        rows = elem.findall(".//TR")
        cells = elem.findall(".//TD") + elem.findall(".//TH")
        for row in rows or [elem]:
            text = _clean(" | ".join(_clean(_text_of(c)) for c in row))
            if text:
                self._add_paragraph(parent, text)
        self._warnings.append(
            {
                "type": "table_flattened",
                "element": elem.tag,
                "section": self._section_of(parent),
                "rows": len(rows),
                "cells": len(cells),
                "message": (
                    f"Table rendered as text ({len(rows)} row(s), {len(cells)} cell(s)); "
                    f"column structure is lost"
                ),
            }
        )

    def _note_unsupported(self, elem: etree._Element, parent: Any, reason: str) -> None:
        self._unknown.append(
            {
                "element": elem.tag,
                "section": self._section_of(parent),
                "message": f"{elem.tag}: {reason}",
            }
        )

    def _parse_container(self, elem: etree._Element, parent: Any) -> int:
        section = RegulationSection()
        section.title = _clean(self._head_text(elem))
        citation = self._citation(elem)
        section.designation = citation.replace("§", "").strip()
        section.level = 1 if elem.tag == "DIV6" else 2
        parent.add_child(section)

        found = 0
        for child in elem:
            found += self._dispatch(child, section)
        return found

    def _parse_section(self, elem: etree._Element, parent: Any) -> None:
        rule = RegulationRequirement()
        head = _clean(self._head_text(elem))
        match = _HEAD_RE.match(head)
        number = elem.get("N") or (match.group("number") if match else "")

        citation = self._citation(elem)
        rule.designation = (citation or f"14 CFR {number}").replace("§", "").strip()
        rule.title = match.group("title").strip() if match else head
        rule.erules_id = ""
        rule.requirement_type = "FAR"
        rule.metadata = {"ecfr": {"section": number, "citation": citation}}
        parent.add_child(rule)

        for child in elem:
            self._dispatch(child, rule)

    def _parse_paragraph(self, elem: etree._Element, parent: Any) -> None:
        para = ParagraphNode()
        self._inline(elem, para)
        if para.children:
            parent.add_child(para)

    def _inline(self, elem: etree._Element, para: ParagraphNode) -> None:
        """Flatten eCFR inline markup (``I``, ``E``) into AST inline nodes."""
        if elem.text:
            para.add_child(TextNode(text=elem.text))
        for child in elem:
            text = _text_of(child)
            if child.tag == "I":
                node: Any = ItalicNode(text=text)
            elif child.tag == "E":
                node = BoldNode(text=text)
            else:
                node = TextNode(text=text)
            if text:
                para.add_child(node)
            if child.tail:
                para.add_child(TextNode(text=child.tail))

    def _add_paragraph(self, parent: Any, text: str) -> None:
        para = ParagraphNode()
        para.add_child(TextNode(text=text))
        parent.add_child(para)

    def normalize_designation(self, text: str) -> str:
        """``§ 23.2000`` / ``FAR 23.2000`` → ``14 CFR 23.2000``."""
        cleaned = " ".join((text or "").replace("§", "").split())
        if not cleaned:
            return ""
        cleaned = re.sub(r"^(?:FAR|14\s*CFR)\s*", "", cleaned, flags=re.IGNORECASE)
        return f"14 CFR {cleaned}" if cleaned else ""


#: Backwards-compatible alias — the scaffold was exported under this name.
FaaAdapter = FaaEcfrAdapter
