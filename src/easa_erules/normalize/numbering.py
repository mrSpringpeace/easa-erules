"""List numbering normalization."""

from __future__ import annotations

from typing import Any

from ..model import ListItemNode, ListNode


def normalize_numbering(root: Any) -> None:
    """Assign sequential numbers to ordered list items when missing."""
    def walk(node: Any) -> None:
        if isinstance(node, ListNode) and node.ordered:
            start = node.start_number or 1
            n = start
            for child in node.children:
                if isinstance(child, ListItemNode):
                    if child.number is None:
                        child.number = n
                    n += 1
        for child in getattr(node, "children", []) or []:
            walk(child)

    walk(root)
