"""EASA list parser."""

from typing import Any

from ..input.namespaces import W, qname
from ..model import ListItemNode, ListNode


class ListParser:
    """Parser for numbered and bulleted lists."""

    def __init__(self, parser):
        self.parser = parser
        self.numbering_defs: dict = {}

    def parse_numbering_definitions(self) -> None:
        """Parse numbering definitions from numbering.xml."""
        if not self.parser.numbering_part:
            return

        root = self.parser.numbering_part.xml()
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        for num in root.findall(".//w:num", namespaces=ns):
            num_id = num.get(qname(W, "numId"))
            if not num_id:
                continue

            abstract_num_id = num.find(".//w:abstractNumId", namespaces=ns)
            if abstract_num_id is not None:
                abstract_id = abstract_num_id.get(qname(W, "val"))
                self.numbering_defs[num_id] = {"abstract_num_id": abstract_id}

    def get_list_level_info(self, num_id: str, level: str) -> dict:
        """Get formatting info for a list level."""
        # This would require parsing abstract numbering definitions
        # Simplified for now
        return {
            "level": level,
            "num_id": num_id,
            "format": "decimal",  # default
        }

    def create_list_from_paragraphs(self, paragraphs: list, parent: Any) -> ListNode | None:
        """Create a list node from consecutive list item paragraphs."""
        if not paragraphs:
            return None

        list_node = ListNode()
        for para in paragraphs:
            item = ListItemNode()
            # Move children from paragraph to list item
            item.children = para.children
            for child in item.children:
                child.parent = item
            list_node.add_child(item)

        parent.add_child(list_node)
        return list_node