"""Structural validation of a parsed Regulation AST."""

from __future__ import annotations

from typing import Any

from ..model import (
    AcceptableMeansOfComplianceNode,
    FigureNode,
    GuidanceNode,
    HeadingNode,
    HyperlinkNode,
    InternalReferenceNode,
    ListNode,
    ParagraphNode,
    RegulationRequirement,
    RegulationSection,
    TableNode,
    TextNode,
)
from .report import ValidationReport


def count_and_check_structure(
    doc: Any,
    report: ValidationReport,
) -> None:
    """Walk the AST, count nodes, and check structural integrity."""
    seen_erules_ids: set[str] = set()
    duplicate_ids: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, RegulationRequirement):
            report.requirements += 1
            report.topics += 1
        elif isinstance(node, RegulationSection):
            report.sections += 1
            report.topics += 1
        elif isinstance(node, GuidanceNode):
            report.guidance += 1
            report.topics += 1
        elif isinstance(node, AcceptableMeansOfComplianceNode):
            report.amc += 1
            report.topics += 1
        elif isinstance(node, ParagraphNode):
            report.paragraphs += 1
        elif isinstance(node, HeadingNode):
            report.headings += 1
        elif isinstance(node, TableNode):
            report.tables += 1
        elif isinstance(node, FigureNode):
            report.images += 1
        elif isinstance(node, ListNode):
            report.lists += 1
        elif isinstance(node, HyperlinkNode):
            report.hyperlinks += 1
        elif isinstance(node, InternalReferenceNode):
            report.internal_references += 1
        elif isinstance(node, TextNode):
            if node.text == "":
                report.empty_text_nodes += 1

        erules_id = getattr(node, "erules_id", None)
        if erules_id:
            if erules_id in seen_erules_ids:
                duplicate_ids.add(erules_id)
            else:
                seen_erules_ids.add(erules_id)

        # Table cells are stored as lists of nodes, not in children
        if isinstance(node, TableNode):
            for row in node.headers + node.rows:
                for cell in row:
                    if isinstance(cell, list):
                        for item in cell:
                            walk(item)
                    else:
                        walk(cell)

        for child in getattr(node, "children", []) or []:
            walk(child)

    walk(doc)

    report.unique_erules_ids = len(seen_erules_ids)
    report.duplicate_erules_ids = sorted(duplicate_ids)

    for dup_id in report.duplicate_erules_ids:
        report.errors.append({
            "type": "duplicate_erules_id",
            "erules_id": dup_id,
            "message": f"Duplicate ERulesId: {dup_id}",
        })

    if report.empty_text_nodes:
        report.warnings.append({
            "type": "empty_text_nodes",
            "count": report.empty_text_nodes,
            "message": f"{report.empty_text_nodes} empty text node(s) found",
        })


def check_source_topic_count(
    report: ValidationReport,
    source_topic_count: int | None,
) -> None:
    """Compare AST topic count against source XML topic count when known."""
    if source_topic_count is None:
        return

    report.source_topic_count = source_topic_count
    if report.topics != source_topic_count:
        report.topic_count_mismatch = True
        report.errors.append({
            "type": "topic_count_mismatch",
            "source_topics": source_topic_count,
            "ast_topics": report.topics,
            "message": (
                f"Topic count mismatch: source XML has {source_topic_count} "
                f"topic(s), AST has {report.topics}"
            ),
        })
