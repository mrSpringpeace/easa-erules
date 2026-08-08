"""EASA topics parser."""

from typing import Any

from lxml import etree

from ..input.namespaces import ERULES
from ..model import (
    AcceptableMeansOfComplianceNode,
    GuidanceNode,
    RegulationRequirement,
    RegulationSection,
)


class TopicParser:
    """Parser for EASA topic elements."""

    def __init__(self, parser):
        self.parser = parser

    def parse(self, elem: etree._Element, parent: Any) -> None:
        """Parse a topic element and its children."""
        # Extract topic metadata
        topic_meta = self._extract_topic_metadata(elem)

        # Determine topic type based on metadata
        topic_type = self._determine_topic_type(topic_meta)

        # Create appropriate AST node
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

        # Parse children
        self._parse_topic_children(elem, node)

        # Add to parent
        parent.add_child(node)

    def _extract_topic_metadata(self, elem: etree._Element) -> dict[str, Any]:
        """Extract metadata from topic element."""
        meta = {}

        # ERulesId
        id_elem = elem.find(f".//{{{ERULES}}}id")
        if id_elem is not None:
            meta["erules_id"] = id_elem.text or ""

        # Title
        title_elem = elem.find(f".//{{{ERULES}}}title")
        if title_elem is not None:
            meta["title"] = title_elem.text or ""

        # Nested metadata
        meta_elem = elem.find(f".//{{{ERULES}}}metadata")
        if meta_elem is not None:
            meta["nested_metadata"] = self._parse_nested_metadata(meta_elem)

        return meta

    def _parse_nested_metadata(self, elem: etree._Element) -> dict[str, Any]:
        """Parse nested metadata within a topic."""
        meta = {}

        for child in elem:
            tag = etree.QName(child.tag).localname
            if child.text:
                if tag in meta:
                    if not isinstance(meta[tag], list):
                        meta[tag] = [meta[tag]]
                    meta[tag].append(child.text)
                else:
                    meta[tag] = child.text

        return meta

    def _determine_topic_type(self, meta: dict[str, Any]) -> str:
        """Determine the type of topic based on metadata."""
        nested = meta.get("nested_metadata", {})

        # Check typeOfContent
        toc = nested.get("typeOfContent", [])
        if isinstance(toc, str):
            toc = [toc]

        for t in toc:
            t_lower = t.lower()
            if "certification" in t_lower or "cs" in t_lower:
                return "requirement"
            if "acceptable means" in t_lower or "amc" in t_lower:
                return "amc"
            if "guidance" in t_lower or "gm" in t_lower:
                return "guidance"

        # Check erules_id pattern
        erules_id = meta.get("erules_id", "")
        if erules_id:
            if "AMC" in erules_id.upper():
                return "amc"
            if "GM" in erules_id.upper():
                return "guidance"

        # Check designation pattern in title
        title = meta.get("title", "")
        if title:
            if title.startswith(("AMC", "amc")):
                return "amc"
            if title.startswith(("GM", "gm")):
                return "guidance"

        return "section"

    def _create_requirement_node(self, meta: dict[str, Any]) -> RegulationRequirement:
        """Create a RegulationRequirement node."""
        node = RegulationRequirement(
            designation=meta.get("title", "").split(" ")[0] if meta.get("title") else "",
            title=meta.get("title", ""),
            erules_id=meta.get("erules_id", ""),
        )
        node.metadata["easa"] = meta.get("nested_metadata", {})
        return node

    def _create_guidance_node(self, meta: dict[str, Any]) -> GuidanceNode:
        """Create a GuidanceNode."""
        node = GuidanceNode(
            designation=meta.get("title", "").split(" ")[0] if meta.get("title") else "",
            title=meta.get("title", ""),
            erules_id=meta.get("erules_id", ""),
        )
        node.metadata["easa"] = meta.get("nested_metadata", {})
        return node

    def _create_amc_node(self, meta: dict[str, Any]) -> AcceptableMeansOfComplianceNode:
        """Create an AMC node."""
        node = AcceptableMeansOfComplianceNode(
            designation=meta.get("title", "").split(" ")[0] if meta.get("title") else "",
            title=meta.get("title", ""),
            erules_id=meta.get("erules_id", ""),
        )
        node.metadata["easa"] = meta.get("nested_metadata", {})
        return node

    def _create_section_node(self, meta: dict[str, Any]) -> RegulationSection:
        """Create a RegulationSection node."""
        node = RegulationSection(
            designation=meta.get("erules_id", ""),
            title=meta.get("title", ""),
        )
        node.metadata["easa"] = meta.get("nested_metadata", {})
        return node

    def _create_generic_section_node(self, meta: dict[str, Any]) -> RegulationSection:
        """Create a generic section node."""
        return self._create_section_node(meta)

    def _parse_topic_children(self, elem: etree._Element, parent: Any) -> None:
        """Parse child elements of a topic."""
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        for child in elem:
            # Skip metadata elements (already parsed)
            if child.tag.startswith(f"{{{ERULES}}}") and etree.QName(child.tag).localname in ("id", "title", "metadata"):
                continue

            # Delegate to main parser
            self.parser._parse_element(child, parent)