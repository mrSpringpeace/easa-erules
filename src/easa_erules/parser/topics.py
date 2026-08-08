"""EASA topics parser."""

from __future__ import annotations

import re
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
from ..util.slugify import extract_designation


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
        text_blob = "".join(content.itertext()) if content is not None else ""
        text_blob = " ".join(text_blob.split())
        title = text_blob[:200] if text_blob else "Untitled topic"
        designation = extract_designation(title) or self._first_line_designation(content)

        topic_meta = {
            "erules_id": designation,
            "title": title if len(title) < 300 else title[:297] + "...",
            "nested_metadata": {},
        }
        upper = title.upper()
        if upper.startswith("AMC") or " ACCEPTABLE MEANS" in upper[:40]:
            node = self._create_amc_node(topic_meta)
        elif upper.startswith("GM") or "GUIDANCE" in upper[:40]:
            node = self._create_guidance_node(topic_meta)
        elif designation or upper.startswith("CS"):
            node = self._create_requirement_node(topic_meta)
        else:
            node = self._create_section_node(topic_meta)

        if content is not None:
            for child in content:
                if isinstance(child.tag, str) and etree.QName(child.tag).localname == "sdt":
                    self.parser._parse_element(child, parent)
                else:
                    self.parser._parse_element(child, node)

        parent.add_child(node)

    def parse_sdt_heading(self, content: etree._Element, parent: Any) -> None:
        """Parse an SDT marked as heading into a RegulationSection."""
        text_blob = " ".join("".join(content.itertext()).split())
        node = RegulationSection(
            designation=extract_designation(text_blob) or "",
            title=text_blob[:200] if text_blob else "Heading",
            level=1,
        )
        for child in content:
            self.parser._parse_element(child, node)
        parent.add_child(node)

    def _first_line_designation(self, content: etree._Element | None) -> str:
        if content is None:
            return ""
        for p in content.findall(f".//{qname(W, 'p')}"):
            text = " ".join("".join(p.itertext()).split())
            if not text:
                continue
            des = extract_designation(text)
            if des:
                return des
            m = re.match(r"(CS[-\s]?[A-Z0-9]+(?:\s+\d+(?:\([a-z]\))?)?)", text, re.I)
            if m:
                return re.sub(r"\s+", "-", m.group(1).strip())
            m = re.match(r"((?:AMC|GM)\s*VLA\s*\d+(?:\([a-z]\))?)", text, re.I)
            if m:
                return re.sub(r"\s+", " ", m.group(1).strip())
            break
        return ""

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
        nested = meta.get("nested_metadata", {})
        toc = nested.get("type_of_content") or nested.get("typeOfContent") or []
        if isinstance(toc, str):
            toc = [toc]

        for t in toc:
            t_lower = t.lower()
            if "certification" in t_lower or t_lower == "cs" or t_lower.startswith("cs "):
                return "requirement"
            if "acceptable means" in t_lower or "amc" in t_lower:
                return "amc"
            if "guidance" in t_lower or t_lower == "gm" or t_lower.startswith("gm "):
                return "guidance"

        erules_id = meta.get("erules_id", "")
        if erules_id:
            if "AMC" in erules_id.upper():
                return "amc"
            if "GM" in erules_id.upper():
                return "guidance"

        title = meta.get("title", "")
        if title:
            if title.startswith(("AMC", "amc")):
                return "amc"
            if title.startswith(("GM", "gm")):
                return "guidance"
            if extract_designation(title):
                return "requirement"

        return "section"

    def _designation_from_meta(self, meta: dict[str, Any]) -> str:
        title = meta.get("title", "") or ""
        designation = extract_designation(title)
        if designation:
            return designation
        erules_id = meta.get("erules_id", "") or ""
        if erules_id and not erules_id.upper().startswith("ERULES"):
            return erules_id
        return title.split(" ")[0] if title else erules_id

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
        node = RegulationSection(
            designation=meta.get("erules_id", "") or self._designation_from_meta(meta),
            title=meta.get("title", ""),
        )
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
