"""EASA paragraph parser."""

from typing import Any

from lxml import etree

from ..input.namespaces import (
    W,
    qname,
)
from ..model import (
    BoldNode,
    HeadingNode,
    HyperlinkNode,
    InternalReferenceNode,
    ItalicNode,
    LineBreakNode,
    ListItemNode,
    ListNode,
    ParagraphNode,
    SubscriptNode,
    SuperscriptNode,
    TextNode,
)
from ..model.references import Reference, ReferenceType


class ParagraphParser:
    """Parser for WordprocessingML paragraphs."""

    def __init__(self, parser):
        self.parser = parser
        self.style_map: dict = {}

    def parse(self, elem: etree._Element, parent: Any) -> ParagraphNode | None:
        """Parse a paragraph element."""
        # Check if it's a heading based on style
        style = self._get_paragraph_style(elem)
        if style and self._is_heading_style(style):
            return self._parse_heading(elem, parent, style)

        # Check if it's a list item
        if self._is_list_item(elem):
            return self._parse_list_item(elem, parent)

        # Regular paragraph — attach first so nested figures can resolve rule context
        para = ParagraphNode()
        parent.add_child(para)
        self._parse_paragraph_content(elem, para)
        return para

    def _get_paragraph_style(self, elem: etree._Element) -> str | None:
        """Get paragraph style ID."""
        ppr = elem.find(qname(W, "pPr"))
        if ppr is not None:
            pstyle = ppr.find(qname(W, "pStyle"))
            if pstyle is not None:
                return pstyle.get(qname(W, "val"))
        return None

    def _is_heading_style(self, style: str) -> bool:
        """Check if style is a heading style."""
        style_lower = style.lower()
        return (
            style_lower.startswith("heading")
            or "head" in style_lower
            or style_lower in ("title", "subtitle")
        )

    def _parse_heading(self, elem: etree._Element, parent: Any, style: str) -> HeadingNode:
        """Parse a heading paragraph."""
        # Determine heading level from style
        level = self._get_heading_level(style)

        heading = HeadingNode(level=level)
        parent.add_child(heading)
        self._parse_paragraph_content(elem, heading)

        # Extract designation from heading text if present
        text = heading.get_text().strip()
        heading.designation = self._extract_designation(text)

        return heading

    def _get_heading_level(self, style: str) -> int:
        """Extract heading level from style name."""
        style_lower = style.lower()
        # Try to extract number from "Heading 1", "Heading1", etc.
        import re
        match = re.search(r"heading\s*(\d+)", style_lower)
        if match:
            return int(match.group(1))
        match = re.search(r"head\s*(\d+)", style_lower)
        if match:
            return int(match.group(1))
        return 1

    def _extract_designation(self, text: str) -> str:
        """Extract designation like 'CS-VLA.303' from heading text."""
        import re
        # Pattern for CS-VLA.303, CS 23.2210, AMC1 CS-23.XXXX, etc.
        patterns = [
            r"(CS[-\s]?[A-Z0-9]+(?:\.\d+)?)",
            r"(AMC\d*\s+CS[-\s]?[A-Z0-9]+(?:\.\d+)?)",
            r"(GM\d*\s+CS[-\s]?[A-Z0-9]+(?:\.\d+)?)",
            r"(\d+\.\d+)",  # Simple numbered sections
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).replace(" ", "-")
        return ""

    def _is_list_item(self, elem: etree._Element) -> bool:
        """Check if paragraph is a list item."""
        ppr = elem.find(qname(W, "pPr"))
        if ppr is not None:
            numpr = ppr.find(qname(W, "numPr"))
            if numpr is not None:
                return True
        return False

    def _get_list_num_id(self, elem: etree._Element) -> str:
        """Get the numId for a list item."""
        ppr = elem.find(qname(W, "pPr"))
        if ppr is not None:
            numpr = ppr.find(qname(W, "numPr"))
            if numpr is not None:
                num_id = numpr.find(qname(W, "numId"))
                if num_id is not None:
                    return num_id.get(qname(W, "val"))
        return "1"

    def _parse_list_item(self, elem: etree._Element, parent: Any) -> ListItemNode:
        """Parse a list item paragraph."""
        item = ListItemNode()

        # Try to get list level and number
        ppr = elem.find(qname(W, "pPr"))
        if ppr is not None:
            numpr = ppr.find(qname(W, "numPr"))
            if numpr is not None:
                ilvl = numpr.find(qname(W, "ilvl"))
                if ilvl is not None:
                    item.metadata["list_level"] = ilvl.get(qname(W, "val"))

        # Get numId for list formatting
        num_id = self._get_list_num_id(elem)

        # Find or create parent list, attach item before parsing content
        # so nested assets can walk the parent chain for naming.
        list_node = self._find_or_create_parent_list(parent, item, num_id)
        list_node.add_child(item)
        self._parse_paragraph_content(elem, item)

        return item

    def _find_or_create_parent_list(self, parent: Any, item: ListItemNode, num_id: str = "1") -> ListNode:
        """Find existing list or create new one."""
        # Check if last child is a list at same level
        if parent.children and isinstance(parent.children[-1], ListNode):
            last_list = parent.children[-1]
            item_level = item.metadata.get("list_level", "0")
            # Simplified: assume same level belongs to same list
            return last_list

        # Create new list with proper ordering
        ordered = self.parser.list_parser.is_ordered(num_id)
        list_node = ListNode(ordered=ordered)
        parent.add_child(list_node)
        return list_node

    def _parse_paragraph_content(self, elem: etree._Element, parent: Any) -> None:
        """Parse paragraph content (runs)."""
        for child in elem:
            tag = etree.QName(child.tag).localname

            if tag == "r":
                self._parse_run(child, parent)
            elif tag == "hyperlink":
                self._parse_hyperlink(child, parent)
            elif tag == "drawing":
                self._parse_drawing(child, parent)
            elif tag == "br":
                parent.add_child(LineBreakNode())
            elif tag == "tab":
                parent.add_child(TextNode(text="\t"))

    def _parse_run(self, elem: etree._Element, parent: Any) -> None:
        """Parse a text run with formatting."""
        rpr = elem.find(qname(W, "rPr"))
        formatting = self._get_run_formatting(rpr)

        text_parts: list[str] = []
        for child in elem:
            if etree.QName(child.tag).localname == "t":
                text = child.text or ""
                # Preserve whitespace
                if child.get(qname(W, "space")) == "preserve":
                    text = text
                text_parts.append(text)
            elif etree.QName(child.tag).localname == "tab":
                text_parts.append("\t")
            elif etree.QName(child.tag).localname == "br":
                text_parts.append("\n")
            elif etree.QName(child.tag).localname == "drawing":
                # Inline drawing in run
                self._parse_drawing(child, parent)

        full_text = "".join(text_parts)
        if not full_text:
            return

        # Split plain text on internal regulatory references when unformatted
        if not any(formatting.get(k) for k in ("bold", "italic", "superscript", "subscript")):
            segments = self._split_text_with_references(full_text, parent)
            if segments is not None:
                for segment in segments:
                    parent.add_child(segment)
                return

        node = self._apply_formatting(full_text, formatting)
        parent.add_child(node)

    def _split_text_with_references(self, text: str, parent: Any) -> list[Any] | None:
        """Split text into TextNode / InternalReferenceNode segments.

        Returns None when no references are found (caller should use plain formatting).
        """
        import re

        # AMC1 CS-TEST.300, GM1 CS-23.1, CS-VLA.303, CS 23.2210
        pattern = re.compile(
            r"(?P<ref>(?:AMC\d*|GM\d*)\s+CS[-\s]?[A-Z0-9]+(?:\.\d+)?|"
            r"CS[-\s]?[A-Z0-9]+(?:\.\d+)+)",
            re.IGNORECASE,
        )
        matches = list(pattern.finditer(text))
        if not matches:
            return None

        segments: list[Any] = []
        cursor = 0
        source_id = getattr(parent, "id", "") or ""

        for match in matches:
            if match.start() > cursor:
                segments.append(TextNode(text=text[cursor:match.start()]))

            raw = match.group("ref")
            designation = re.sub(r"\s+", " ", raw).strip()
            # Normalize "CS 23.2210" -> "CS-23.2210", keep "AMC1 CS-TEST.300"
            if designation.upper().startswith(("AMC", "GM")):
                designation = re.sub(
                    r"(AMC\d*|GM\d*)\s+CS\s+",
                    lambda m: f"{m.group(1)} CS-",
                    designation,
                    flags=re.IGNORECASE,
                )
                designation = re.sub(r"\s+", " ", designation)
            else:
                designation = designation.replace(" ", "-")

            ref_node = InternalReferenceNode(
                text=raw,
                target_id="",
                target_designation=designation,
            )
            ref_node.add_child(TextNode(text=raw))
            segments.append(ref_node)

            # Register for later resolution
            self.parser.references.add(
                Reference(
                    source_id=source_id,
                    target_id="",
                    target_designation=designation,
                    reference_type=ReferenceType.INTERNAL,
                    raw_text=raw,
                    resolved=False,
                )
            )
            cursor = match.end()

        if cursor < len(text):
            segments.append(TextNode(text=text[cursor:]))

        return segments

    def _get_run_formatting(self, rpr: etree._Element | None) -> dict:
        """Extract formatting properties from run properties."""
        fmt = {
            "bold": False,
            "italic": False,
            "underline": False,
            "superscript": False,
            "subscript": False,
            "size": None,
            "style": None,
        }

        if rpr is None:
            return fmt

        if rpr.find(qname(W, "b")) is not None:
            fmt["bold"] = True
        if rpr.find(qname(W, "i")) is not None:
            fmt["italic"] = True
        if rpr.find(qname(W, "u")) is not None:
            fmt["underline"] = True

        vert_align = rpr.find(qname(W, "vertAlign"))
        if vert_align is not None:
            val = vert_align.get(qname(W, "val"))
            if val == "superscript":
                fmt["superscript"] = True
            elif val == "subscript":
                fmt["subscript"] = True

        sz = rpr.find(qname(W, "sz"))
        if sz is not None:
            fmt["size"] = sz.get(qname(W, "val"))

        rstyle = rpr.find(qname(W, "rStyle"))
        if rstyle is not None:
            fmt["style"] = rstyle.get(qname(W, "val"))

        return fmt

    def _apply_formatting(self, text: str, formatting: dict) -> Any:
        """Apply formatting to text, creating appropriate inline nodes."""
        # Build nested formatting nodes (innermost first)
        node: Any = TextNode(text=text)

        # Apply in order: superscript, subscript, bold, italic
        # (Order matters for nesting, but all should preserve text)
        if formatting["superscript"]:
            node = SuperscriptNode(text=text, children=[node])
        if formatting["subscript"]:
            node = SubscriptNode(text=text, children=[node])
        if formatting["bold"]:
            node = BoldNode(text=text, children=[node])
        if formatting["italic"]:
            node = ItalicNode(text=text, children=[node])

        return node

    def _parse_hyperlink(self, elem: etree._Element, parent: Any) -> None:
        """Parse a hyperlink."""
        # Relationship ID (r:id is in the office document relationships namespace)
        from ..input.namespaces import OFFICE_DOC_REL
        rel_id = elem.get(f"{{{OFFICE_DOC_REL}}}id")

        # Get link text
        link_text = ""
        for child in elem:
            if etree.QName(child.tag).localname == "r":
                for grandchild in child:
                    if etree.QName(grandchild.tag).localname == "t":
                        link_text += grandchild.text or ""

        # Resolve URL via relationships
        url = self._resolve_hyperlink_url(rel_id)

        if link_text and url:
            from ..model import TextNode
            node = HyperlinkNode(text=link_text, url=url)
            # Add text as child for proper rendering
            text_node = TextNode(text=link_text)
            node.add_child(text_node)
            parent.add_child(node)

    def _resolve_hyperlink_url(self, rel_id: str | None) -> str | None:
        """Resolve hyperlink URL via package relationships."""
        if not rel_id or not self.parser.doc_part:
            return None

        # First check document part relationships
        rels = self.parser.doc_part.relationships
        if rels:
            rel = rels.get(rel_id)
            if rel and rel.type == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink":
                return rel.target

        # Fallback to package-level relationships (for Flat OPC)
        if self.parser.package._package_relationships:
            rel = self.parser.package._package_relationships.get(rel_id)
            if rel and rel.type == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink":
                return rel.target

        return None

    def _parse_drawing(self, elem: etree._Element, parent: Any) -> None:
        """Parse a drawing (image) element."""
        # Delegate to figure parser
        self.parser.figure_parser.parse_inline_drawing(elem, parent)