"""EASA topics parser (custom XML topics and Word SDT wrappers)."""

from __future__ import annotations

from typing import Any

from lxml import etree

from ..input.namespaces import ERULES, ERULES_NAMESPACES, W, qname
from ..model import (
    AcceptableMeansOfComplianceNode,
    GuidanceNode,
    RegulationRequirement,
    RegulationSection,
)
from ..model.metadata import normalize_easa_metadata_dict
from ..util.slugify import (
    extract_designation,
    extract_designation_from_lines,
    extract_ed_decision,
)


class TopicParser:
    """Parser for EASA topic elements (custom XML and Word SDT wrappers)."""

    def __init__(self, parser):
        self.parser = parser

    def parse(self, elem: etree._Element, parent: Any) -> None:
        """Parse a custom-XML topic element and its children."""
        topic_meta = self._extract_topic_metadata(elem)
        topic_type = self._determine_topic_type(topic_meta)

        if topic_type == "requirement":
            node = self._create_requirement_node(topic_meta)
        elif topic_type == "guidance":
            node = self._create_guidance_node(topic_meta)
        elif topic_type == "amc":
            node = self._create_amc_node(topic_meta)
        elif topic_type == "section":
            node = self._create_section_node(topic_meta)
        else:
            node = self._create_generic_section_node(topic_meta)

        self._parse_topic_children(elem, node)
        parent.add_child(node)

    def parse_sdt(self, sdt: etree._Element, content: etree._Element | None, parent: Any) -> None:
        """Parse a Word SDT-wrapped topic (official EAR XML export)."""
        sdt_id = self._sdt_id(sdt)
        export = None
        meta_parser = getattr(self.parser, "metadata_parser", None)
        if meta_parser is not None:
            export = meta_parser.topic_meta_for_sdt(sdt_id)

        lines = self._content_lines(content)
        first_line = lines[0] if lines else ""
        body_blob = " ".join(lines) if lines else ""

        # Prefer export source-title, then first content line (not full body blob)
        if export and export.get("source_title"):
            title = str(export["source_title"]).replace("\xa0", " ").strip()
        elif first_line:
            title = first_line[:300]
        elif body_blob:
            title = body_blob[:297] + ("..." if len(body_blob) > 300 else "")
        else:
            title = "Untitled topic"

        # Designation: title first, then first few lines — never full body
        designation = extract_designation(title, require_number=True)
        if not designation:
            designation = extract_designation_from_lines(lines[:3])
        if not designation:
            # Bare document-level code only if title is short (e.g. section codes)
            designation = extract_designation(title, require_number=False)
            if designation and len(title) > len(designation) + 8:
                # Likely false positive from mid-title noise
                designation = ""

        erules_id = ""
        if export and export.get("erules_id"):
            erules_id = str(export["erules_id"])
        if not erules_id:
            erules_id = designation

        nested: dict[str, Any] = {}
        if export:
            nested = {k: v for k, v in export.items() if k not in ("raw_attributes",)}

        # ED Decision from second line is a common EAR pattern
        if not nested.get("regulatory_source"):
            for line in lines[:3]:
                ed = extract_ed_decision(line)
                if ed:
                    nested["regulatory_source"] = [ed]
                    break

        if sdt_id and not nested.get("sdt_id"):
            nested["sdt_id"] = sdt_id

        topic_meta = {
            "erules_id": erules_id,
            "title": title,
            "nested_metadata": nested,
            "designation_hint": designation,
        }

        topic_type = self._determine_topic_type(topic_meta)
        if topic_type == "requirement":
            node = self._create_requirement_node(topic_meta)
        elif topic_type == "guidance":
            node = self._create_guidance_node(topic_meta)
        elif topic_type == "amc":
            node = self._create_amc_node(topic_meta)
        else:
            node = self._create_section_node(topic_meta)

        if content is not None:
            for child in content:
                if isinstance(child.tag, str) and etree.QName(child.tag).localname == "sdt":
                    # Nested SDT topics attach to the document parent, not this topic
                    self.parser._parse_element(child, parent)
                else:
                    self.parser._parse_element(child, node)

        parent.add_child(node)

    def parse_sdt_heading(self, content: etree._Element, parent: Any) -> None:
        """Parse an SDT marked as heading into a RegulationSection."""
        lines = self._content_lines(content)
        text_blob = lines[0] if lines else " ".join("".join(content.itertext()).split())
        designation = extract_designation(text_blob, require_number=True) or ""
        node = RegulationSection(
            designation=designation,
            title=text_blob[:200] if text_blob else "Heading",
            level=1,
        )
        for child in content:
            self.parser._parse_element(child, node)
        parent.add_child(node)

    def _sdt_id(self, sdt: etree._Element) -> str | None:
        """Return Word SDT id value from sdtPr/id/@w:val."""
        sdt_pr = sdt.find(qname(W, "sdtPr"))
        if sdt_pr is None:
            sdt_pr = sdt.find(f".//{qname(W, 'sdtPr')}")
        if sdt_pr is None:
            return None
        id_el = sdt_pr.find(qname(W, "id"))
        if id_el is None:
            return None
        return id_el.get(qname(W, "val"))

    def _content_lines(self, content: etree._Element | None) -> list[str]:
        if content is None:
            return []
        lines: list[str] = []
        for p in content.findall(f".//{qname(W, 'p')}"):
            text = " ".join("".join(p.itertext()).split())
            text = text.replace("\xa0", " ").strip()
            if text:
                lines.append(text)
            if len(lines) >= 12:
                break
        return lines

    def _extract_topic_metadata(self, elem: etree._Element) -> dict[str, Any]:
        """Extract metadata from topic element."""
        meta: dict[str, Any] = {}

        id_elem = elem.find(f"{{{ERULES}}}id")
        if id_elem is None:
            id_elem = elem.find(f".//{{{ERULES}}}id")
        if id_elem is not None:
            meta["erules_id"] = id_elem.text or ""

        title_elem = elem.find(f"{{{ERULES}}}title")
        if title_elem is None:
            title_elem = elem.find(f".//{{{ERULES}}}title")
        if title_elem is not None:
            meta["title"] = title_elem.text or ""

        meta_elem = elem.find(f"{{{ERULES}}}metadata")
        if meta_elem is None:
            meta_elem = elem.find(f".//{{{ERULES}}}metadata")
        if meta_elem is not None:
            meta["nested_metadata"] = self._parse_nested_metadata(meta_elem)

        return meta

    def _parse_nested_metadata(self, elem: etree._Element) -> dict[str, Any]:
        """Parse nested metadata within a topic into normalized field names."""
        raw: dict[str, Any] = {}
        for child in elem:
            if not isinstance(child.tag, str):
                continue
            tag = etree.QName(child.tag).localname
            if child.text:
                if tag in raw:
                    if not isinstance(raw[tag], list):
                        raw[tag] = [raw[tag]]
                    raw[tag].append(child.text)
                else:
                    raw[tag] = child.text
        return normalize_easa_metadata_dict(raw)

    def _determine_topic_type(self, meta: dict[str, Any]) -> str:
        """Determine the type of topic based on metadata."""
        nested = meta.get("nested_metadata", {}) or {}
        toc = nested.get("type_of_content") or nested.get("typeOfContent") or []
        if isinstance(toc, str):
            toc = [toc]

        for t in toc:
            t_lower = str(t).lower()
            if "acceptable means" in t_lower or t_lower.startswith("amc"):
                return "amc"
            if "guidance" in t_lower or t_lower.startswith("gm"):
                return "guidance"
            if "certification" in t_lower or t_lower == "cs" or t_lower.startswith(("cs ", "cs (")):
                return "requirement"

        erules_id = meta.get("erules_id", "") or ""
        title = meta.get("title", "") or ""
        designation = meta.get("designation_hint") or extract_designation(
            title, require_number=True
        )

        for candidate in (title, designation, erules_id):
            upper = (candidate or "").upper().strip()
            if upper.startswith("AMC"):
                return "amc"
            if upper.startswith("GM"):
                return "guidance"

        if designation or extract_designation(title, require_number=True):
            return "requirement"

        # Fixture titles like CS-VLA.303 Factor of safety
        if extract_designation(title, require_number=False) and title.upper().startswith("CS"):
            return "requirement"

        return "section"

    def _designation_from_meta(self, meta: dict[str, Any]) -> str:
        if meta.get("designation_hint"):
            return str(meta["designation_hint"])
        title = meta.get("title", "") or ""
        designation = extract_designation(title, require_number=True)
        if not designation:
            designation = extract_designation(title, require_number=False)
        if designation:
            return designation
        erules_id = meta.get("erules_id", "") or ""
        # Do not use opaque ERULES-* ids as human designations
        if erules_id and not erules_id.upper().startswith("ERULES"):
            return erules_id
        return ""

    def _easa_metadata_for_node(self, meta: dict[str, Any]) -> dict[str, Any]:
        easa = dict(meta.get("nested_metadata") or {})
        if meta.get("erules_id") and not easa.get("erules_id"):
            easa["erules_id"] = meta["erules_id"]
        if meta.get("title") and not easa.get("source_title"):
            easa["source_title"] = meta["title"]
        return easa

    def _create_requirement_node(self, meta: dict[str, Any]) -> RegulationRequirement:
        node = RegulationRequirement(
            designation=self._designation_from_meta(meta),
            title=meta.get("title", ""),
            erules_id=meta.get("erules_id", ""),
        )
        node.metadata["easa"] = self._easa_metadata_for_node(meta)
        return node

    def _create_guidance_node(self, meta: dict[str, Any]) -> GuidanceNode:
        node = GuidanceNode(
            designation=self._designation_from_meta(meta),
            title=meta.get("title", ""),
            erules_id=meta.get("erules_id", ""),
        )
        node.metadata["easa"] = self._easa_metadata_for_node(meta)
        return node

    def _create_amc_node(self, meta: dict[str, Any]) -> AcceptableMeansOfComplianceNode:
        node = AcceptableMeansOfComplianceNode(
            designation=self._designation_from_meta(meta),
            title=meta.get("title", ""),
            erules_id=meta.get("erules_id", ""),
        )
        node.metadata["easa"] = self._easa_metadata_for_node(meta)
        return node

    def _create_section_node(self, meta: dict[str, Any]) -> RegulationSection:
        designation = self._designation_from_meta(meta)
        # Prefer human designation; fall back to empty rather than opaque ids
        node = RegulationSection(
            designation=designation,
            title=meta.get("title", ""),
        )
        if meta.get("erules_id"):
            # Sections don't always have erules_id field; stash in metadata
            pass
        node.metadata["easa"] = self._easa_metadata_for_node(meta)
        return node

    def _create_generic_section_node(self, meta: dict[str, Any]) -> RegulationSection:
        return self._create_section_node(meta)

    def _parse_topic_children(self, elem: etree._Element, parent: Any) -> None:
        """Parse child elements of a topic."""
        for child in elem:
            if isinstance(child.tag, str):
                ns = etree.QName(child.tag).namespace or ""
                local = etree.QName(child.tag).localname
                if ns in ERULES_NAMESPACES and local in ("id", "title", "metadata"):
                    continue
            self.parser._parse_element(child, parent)
