"""Heading level normalization."""

from __future__ import annotations

from typing import Any

from ..model import HeadingNode


def normalize_headings(root: Any) -> None:
    """Clamp heading levels to 1..6 and fill missing levels heuristically."""
    def walk(node: Any) -> None:
        if isinstance(node, HeadingNode):
            if node.level < 1:
                node.level = 1
            elif node.level > 6:
                node.level = 6
        for child in getattr(node, "children", []) or []:
            walk(child)

    walk(root)
