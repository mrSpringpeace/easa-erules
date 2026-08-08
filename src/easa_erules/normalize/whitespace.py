"""Whitespace normalization for Regulation AST."""

from __future__ import annotations

import re
from typing import Any

from ..model import InlineNode, ParagraphNode, TextNode


def normalize_whitespace(root: Any) -> None:
    """Normalize whitespace in text/inline nodes (in-place).

    - Collapse runs of spaces/tabs (preserve intentional newlines as single space in paragraphs)
    - Strip leading/trailing whitespace on plain TextNodes that are sole paragraph content
    """
    def walk(node: Any) -> None:
        if isinstance(node, TextNode):
            node.text = _collapse(node.text)
        elif isinstance(node, InlineNode) and getattr(node, "text", None) is not None:
            # Keep wrapper text in sync with children when both present
            if node.children:
                node.text = _collapse(node.text) if node.text else node.text
            else:
                node.text = _collapse(node.text)

        if isinstance(node, ParagraphNode):
            _trim_paragraph_edges(node)

        for child in getattr(node, "children", []) or []:
            walk(child)

    walk(root)


def _collapse(text: str) -> str:
    if not text:
        return text
    # Preserve non-breaking intent lightly: collapse horizontal whitespace
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text


def _trim_paragraph_edges(para: ParagraphNode) -> None:
    """Strip leading/trailing whitespace from first/last text-like children."""
    children = para.children
    if not children:
        return
    first = children[0]
    if isinstance(first, TextNode):
        first.text = first.text.lstrip()
    last = children[-1]
    if isinstance(last, TextNode):
        last.text = last.text.rstrip()
