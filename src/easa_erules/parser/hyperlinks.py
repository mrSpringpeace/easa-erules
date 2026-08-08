"""EASA hyperlink parser."""

from typing import Any

from lxml import etree

from ..input.namespaces import W, qname
from ..model import HyperlinkNode, InternalReferenceNode
from ..model.references import Reference, ReferenceType


class HyperlinkParser:
    """Parser for hyperlinks and internal references."""

    def __init__(self, parser):
        self.parser = parser

    def parse_hyperlink(self, elem: etree._Element, parent: Any) -> None:
        """Parse a hyperlink element."""
        # Get relationship ID
        rel_id = elem.get(qname(W, "hyperlink", "r:id"))

        # Extract link text
        link_text = ""
        for child in elem.iter():
            if etree.QName(child.tag).localname == "t":
                link_text += child.text or ""

        if not link_text:
            return

        # Try to resolve as external hyperlink first
        url = self._resolve_external_url(rel_id)
        if url:
            node = HyperlinkNode(text=link_text, url=url)
            parent.add_child(node)
            return

        # Try to resolve as internal reference
        internal_ref = self._resolve_internal_reference(link_text)
        if internal_ref:
            node = InternalReferenceNode(
                text=link_text,
                target_id=internal_ref.target_id,
                target_designation=internal_ref.target_designation,
            )
            parent.add_child(node)
            return

        # Fallback: treat as plain text with reference metadata
        node = InternalReferenceNode(
            text=link_text,
            target_id="",
            target_designation=link_text,
        )
        parent.add_child(node)

    def _resolve_external_url(self, rel_id: str | None) -> str | None:
        """Resolve external hyperlink URL via relationships."""
        if not rel_id or not self.parser.doc_part or not self.parser.doc_part.relationships:
            return None

        rel = self.parser.doc_part.relationships.get(rel_id)
        if rel and rel.is_external:
            return rel.target

        return None

    def _resolve_internal_reference(self, text: str) -> Reference | None:
        """Try to resolve text as internal reference (e.g., CS-VLA.303)."""
        import re

        # Common EASA reference patterns
        patterns = [
            r"(CS[-\s]?[A-Z0-9]+(?:\.\d+)?)",  # CS-VLA.303, CS 23.2210
            r"(AMC\d*\s+CS[-\s]?[A-Z0-9]+(?:\.\d+)?)",  # AMC1 CS-23.XXXX
            r"(GM\d*\s+CS[-\s]?[A-Z0-9]+(?:\.\d+)?)",  # GM1 CS-23.XXXX
            r"(Part\s+\d+)",  # Part 21
            r"(Appendix\s+[A-Z])",  # Appendix A
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                designation = match.group(1).strip().replace(" ", "-")
                # Look up in reference index
                ref = self.parser.references.resolve(designation)
                if ref:
                    return ref

        return None

    def register_reference(self, source_id: str, target_designation: str, ref_type: ReferenceType = ReferenceType.INTERNAL) -> Reference:
        """Register a reference for later resolution."""
        ref = Reference(
            source_id=source_id,
            target_id="",
            target_designation=target_designation,
            reference_type=ref_type,
            raw_text=target_designation,
        )
        self.parser.references.add(ref)
        return ref