"""Reference text normalization on the AST."""

from __future__ import annotations

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
    from ..util.slugify import normalize_designation

    return normalize_designation(text)
