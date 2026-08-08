"""Normalization pipeline applied after parse, before render/index."""

from __future__ import annotations

from typing import Any

from .headings import normalize_headings
from .numbering import normalize_numbering
from .references import normalize_references
from .whitespace import normalize_whitespace


def normalize_document(root: Any) -> Any:
    """Run all normalization passes in-place and return the root."""
    normalize_whitespace(root)
    normalize_headings(root)
    normalize_numbering(root)
    normalize_references(root)
    return root


__all__ = [
    "normalize_document",
    "normalize_headings",
    "normalize_numbering",
    "normalize_references",
    "normalize_whitespace",
]
