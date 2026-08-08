"""Validation package — parse-time and output integrity checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import __version__
from .assets import check_figure_assets, check_output_assets
from .links import check_internal_references
from .output import validate_conversion
from .report import ValidationReport
from .structure import check_source_topic_count, count_and_check_structure

__all__ = [
    "ValidationReport",
    "validate_document",
    "validate_conversion",
    "build_conversion_report",
]


def validate_document(
    doc: Any,
    assets: Any = None,
    references: Any = None,
    parse_warnings: list[dict[str, Any]] | None = None,
    unknown_elements: list[dict[str, Any]] | None = None,
    source_topic_count: int | None = None,
) -> ValidationReport:
    """Validate a parsed document for integrity (content-loss checks).

    Checks:
    - unique ERulesIds
    - structural counts (topics, paragraphs, tables, figures, …)
    - figure assets present in the collection
    - internal references resolved or flagged
    - source topic count vs AST (when provided)
    - unknown XML elements reported
    """
    report = ValidationReport(parser_version=__version__)

    count_and_check_structure(doc, report)
    check_source_topic_count(report, source_topic_count)
    check_figure_assets(doc, report, assets)
    check_internal_references(doc, report, references)

    if parse_warnings:
        for w in parse_warnings:
            if isinstance(w, dict):
                report.warnings.append(w if "type" in w else {"type": "parse_warning", **w})
            else:
                report.warnings.append({"type": "parse_warning", "message": str(w)})

    if unknown_elements:
        report.unknown_elements.extend(unknown_elements)
        report.warnings.append({
            "type": "unknown_elements",
            "count": len(unknown_elements),
            "message": f"{len(unknown_elements)} unknown XML element(s) encountered",
        })

    return report.finalize()


def build_conversion_report(
    doc: Any,
    assets: Any = None,
    references: Any = None,
    parse_warnings: list[dict[str, Any]] | None = None,
    unknown_elements: list[dict[str, Any]] | None = None,
    source_topic_count: int | None = None,
    output_dir: Path | None = None,
) -> ValidationReport:
    """Build a full conversion report, optionally including on-disk checks."""
    report = validate_document(
        doc,
        assets=assets,
        references=references,
        parse_warnings=parse_warnings,
        unknown_elements=unknown_elements,
        source_topic_count=source_topic_count,
    )

    if output_dir is not None:
        # Merge disk asset checks into the same report
        disk = ValidationReport()
        check_output_assets(Path(output_dir), disk)
        for path in disk.missing_images:
            if path not in report.missing_images:
                report.missing_images.append(path)
        for err in disk.errors:
            report.errors.append(err)
        # Prefer on-disk image count when assets were written
        if disk.images:
            report.images = max(report.images, disk.images)

    return report.finalize()
