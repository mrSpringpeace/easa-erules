"""Utilities package."""

from .logging import get_logger, setup_logging
from .slugify import extract_designation, slugify, slugify_rule

__all__ = [
    "extract_designation",
    "get_logger",
    "setup_logging",
    "slugify",
    "slugify_rule",
]