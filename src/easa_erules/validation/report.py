"""Conversion / validation report model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import __version__


@dataclass
class ValidationReport:
    """Report from parse-time or output-directory validation.

    Aligns with the project brief §20 conversion-report.json shape.
    """

    # Counts
    topics: int = 0
    paragraphs: int = 0
    tables: int = 0
    images: int = 0
    lists: int = 0
    requirements: int = 0
    sections: int = 0
    guidance: int = 0
    amc: int = 0
    headings: int = 0
    hyperlinks: int = 0
    internal_references: int = 0

    # Identity / integrity
    unique_erules_ids: int = 0
    duplicate_erules_ids: list[str] = field(default_factory=list)
    source_topic_count: int | None = None
    topic_count_mismatch: bool = False

    # Issues
    unresolved_references: list[dict[str, Any]] = field(default_factory=list)
    missing_images: list[str] = field(default_factory=list)
    unresolved_relationships: list[dict[str, Any]] = field(default_factory=list)
    empty_text_nodes: int = 0
    unknown_elements: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    # Meta
    parser_version: str = __version__
    ok: bool = True
    #: Provenance of the converted publication, when known (see sources.provenance)
    source: dict[str, Any] | None = None

    def finalize(self) -> ValidationReport:
        """Recompute overall ok flag from errors and hard failures."""
        hard = bool(self.errors) or bool(self.duplicate_erules_ids) or bool(self.missing_images)
        if self.topic_count_mismatch:
            hard = True
        self.ok = not hard
        return self

    def to_dict(self) -> dict[str, Any]:
        from ..contract import SCHEMA_VERSION

        return {
            "schema_version": SCHEMA_VERSION,
            "ok": self.ok,
            "parser_version": self.parser_version,
            "source": self.source,
            "topics": self.topics,
            "paragraphs": self.paragraphs,
            "tables": self.tables,
            "images": self.images,
            "lists": self.lists,
            "requirements": self.requirements,
            "sections": self.sections,
            "guidance": self.guidance,
            "amc": self.amc,
            "headings": self.headings,
            "hyperlinks": self.hyperlinks,
            "internal_references": self.internal_references,
            "unique_erules_ids": self.unique_erules_ids,
            "duplicate_erules_ids": self.duplicate_erules_ids,
            "source_topic_count": self.source_topic_count,
            "topic_count_mismatch": self.topic_count_mismatch,
            "unresolved_references": self.unresolved_references,
            "missing_images": self.missing_images,
            "unresolved_relationships": self.unresolved_relationships,
            "empty_text_nodes": self.empty_text_nodes,
            "unknown_elements": self.unknown_elements,
            "warnings": self.warnings,
            "errors": self.errors,
        }
