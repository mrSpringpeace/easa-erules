"""Reference text normalization on the AST."""

from __future__ import annotations

import re
from typing import Any

from ..model import InternalReferenceNode


def normalize_references(root: Any) -> None:
    """Normalize internal reference designations (spacing / CS- form)."""
    def walk(node: Any) -> None:
        if isinstance(node, InternalReferenceNode) and node.target_designation:
            node.target_designation = _normalize_designation(node.target_designation)
        for child in getattr(node, "children", []) or []:
            walk(child)

    walk(root)


def _normalize_designation(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    # CS 23.2210 → CS-23.2210
    text = re.sub(r"\bCS\s+(\d)", r"CS-\1", text, flags=re.I)
    # Collapse multiple hyphens
    text = re.sub(r"-{2,}", "-", text)
    return text
