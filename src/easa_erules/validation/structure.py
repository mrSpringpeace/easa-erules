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


def _topic_identity(node: Any) -> tuple[str, str, str]:
    """What makes two nodes the same published item: label, title and body.

    Comparing bodies alone is not enough — two different rules sharing an
    ERulesId both have their own designation, and that is a real conflict even
    if the AST happens to hold no paragraphs for either.
    """
    return (
        getattr(node, "designation", "") or "",
        getattr(node, "title", "") or "",
        _topic_text(node),
    )


def _topic_text(node: Any) -> str:
    """Flatten a topic's own paragraphs, without descending into nested topics."""
    parts: list[str] = []
    nested = (
        RegulationRequirement,
        RegulationSection,
        GuidanceNode,
        AcceptableMeansOfComplianceNode,
    )

    def walk(n: Any) -> None:
        if isinstance(n, ParagraphNode):
            text = n.get_text().strip()
            if text:
                parts.append(text)
        for child in getattr(n, "children", []) or []:
            if isinstance(child, nested):
                continue
            walk(child)

    walk(node)
    return "\n".join(parts)


def count_and_check_structure(
    doc: Any,
    report: ValidationReport,
) -> None:
    """Walk the AST, count nodes, and check structural integrity."""
    # An AMC or GM that relates to several rules is printed once under each of
    # them, carrying the same ERulesId every time. That is how EASA publishes
    # it, not a parse failure — so repeats of an identical body are recorded
    # and repeats with differing bodies are errors.
    items_by_erules_id: dict[str, list[tuple[str, str, str]]] = {}

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
            items_by_erules_id.setdefault(erules_id, []).append(_topic_identity(node))

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

    report.unique_erules_ids = len(items_by_erules_id)

    repeated: dict[str, int] = {}
    conflicting: list[str] = []
    for erules_id, items in items_by_erules_id.items():
        if len(items) < 2:
            continue
        if len(set(items)) == 1:
            repeated[erules_id] = len(items)
        else:
            conflicting.append(erules_id)

    report.repeated_erules_ids = dict(sorted(repeated.items()))
    report.duplicate_erules_ids = sorted(conflicting)

    if repeated:
        report.warnings.append({
            "type": "repeated_erules_ids",
            "count": len(repeated),
            "occurrences": sum(repeated.values()),
            "message": (
                f"{len(repeated)} item(s) published more than once with identical "
                f"content (AMC/GM covering several rules); "
                f"{sum(repeated.values())} occurrences in total"
            ),
        })

    for dup_id in report.duplicate_erules_ids:
        report.errors.append({
            "type": "conflicting_erules_id",
            "erules_id": dup_id,
            "message": (
                f"ERulesId {dup_id} is used by items with different content — "
                f"the id no longer identifies one item"
            ),
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
