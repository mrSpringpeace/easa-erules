"""EASA list parser."""

from typing import Any

from ..input.namespaces import W, qname
from ..model import ListItemNode, ListNode


class ListParser:
    """Parser for numbered and bulleted lists."""

    def __init__(self, parser):
        self.parser = parser
        self.numbering_defs: dict = {}  # num_id -> {abstract_num_id, format}

    def parse_numbering_definitions(self) -> None:
        """Parse numbering definitions from numbering.xml."""
        if not self.parser.numbering_part:
            return

        root = self.parser.numbering_part.xml()
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        # First, parse abstract numbering definitions
        abstract_defs = {}
        for abstract_num in root.findall(".//w:abstractNum", namespaces=ns):
            abstract_id = abstract_num.get(qname(W, "abstractNumId"))
            if not abstract_id:
                continue
            
            # Get the numbering format from the first level
            lvl = abstract_num.find(".//w:lvl", namespaces=ns)
            if lvl is not None:
                num_fmt = lvl.find(qname(W, "numFmt"))
                if num_fmt is not None:
                    fmt = num_fmt.get(qname(W, "val"))
                    abstract_defs[abstract_id] = fmt

        # Then parse concrete numbering instances
        for num in root.findall(".//w:num", namespaces=ns):
            num_id = num.get(qname(W, "numId"))
            if not num_id:
                continue

            abstract_num_id = num.find(".//w:abstractNumId", namespaces=ns)
            if abstract_num_id is not None:
                abstract_id = abstract_num_id.get(qname(W, "val"))
                fmt = abstract_defs.get(abstract_id, "decimal")
                self.numbering_defs[num_id] = {"format": fmt}

    def get_list_format(self, num_id: str) -> str:
        """Get the numbering format for a num_id."""
        return self.numbering_defs.get(num_id, {}).get("format", "decimal")

    def is_ordered(self, num_id: str) -> bool:
        """Check if a list is ordered (decimal, upperLetter, etc.) vs bullet."""
        fmt = self.get_list_format(num_id)
        # Bullet formats
        if fmt in ("bullet", "none"):
            return False
        return True

    def create_list_from_paragraphs(self, paragraphs: list, parent: Any, num_id: str = "1") -> ListNode | None:
        """Create a list node from consecutive list item paragraphs."""
        if not paragraphs:
            return None

        ordered = self.is_ordered(num_id)
        list_node = ListNode(ordered=ordered)
        
        for para in paragraphs:
            item = ListItemNode()
            # Move children from paragraph to list item
            item.children = para.children
            for child in item.children:
                child.parent = item
            list_node.add_child(item)

        parent.add_child(list_node)
        return list_node