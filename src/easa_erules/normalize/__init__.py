"""Normalization pipeline applied after parse, before render/index."""

from __future__ import annotations

from typing import Any

from .headings import normalize_headings
from .numbering import normalize_numbering
from .refdetect import detect_text_references, find_designations
from .references import normalize_references
from .whitespace import normalize_whitespace


def normalize_document(
    root: Any,
    *,
    detect_references: bool = True,
    authority: str = "",
) -> Any:
    """Run all normalization passes in-place and return the root."""
    normalize_whitespace(root)
    normalize_headings(root)
    normalize_numbering(root)
    if detect_references:
        detect_text_references(root, authority=authority)
    normalize_references(root)
    return root


__all__ = [
    "detect_text_references",
    "find_designations",
    "normalize_document",
    "normalize_headings",
    "normalize_numbering",
    "normalize_references",
    "normalize_whitespace",
]
