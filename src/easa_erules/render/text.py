"""Deterministic plain-text and feature extraction from AST nodes."""

from __future__ import annotations

from typing import Any

from ..model import FigureNode, InlineNode, ParagraphNode, TableNode


def plain_text(node: Any, *, include_nested_topics: bool = False) -> str:
    """Flatten user-visible text, including tables and figure descriptions."""
    from ..model import (
        AcceptableMeansOfComplianceNode,
        GuidanceNode,
        RegulationRequirement,
        RegulationSection,
    )

    topic_types = (
        RegulationRequirement,
        GuidanceNode,
        AcceptableMeansOfComplianceNode,
        RegulationSection,
    )
    parts: list[str] = []

    def add(value: Any) -> None:
        text = " ".join(str(value or "").split())
        if text:
            parts.append(text)

    def walk(current: Any, *, root: bool = False) -> None:
        if isinstance(current, ParagraphNode):
            add(current.get_text())
            for child in getattr(current, "children", []) or []:
                if not isinstance(child, InlineNode):
                    walk(child)
            return
        elif isinstance(current, InlineNode):
            add(current.text)
        elif isinstance(current, TableNode):
            add(current.caption)
            for row in [*current.headers, *current.rows]:
                for cell in row:
                    if isinstance(cell, list):
                        for item in cell:
                            walk(item)
                    else:
                        walk(cell)
        elif isinstance(current, FigureNode):
            add(current.caption)
            add(current.alt_text)

        for child in getattr(current, "children", []) or []:
            if not include_nested_topics and isinstance(child, topic_types):
                continue
            walk(child)

    add(getattr(node, "title", ""))
    walk(node, root=True)
    # Preserve order while removing duplicate adjacent/indexed fragments.
    deduped: list[str] = []
    for value in parts:
        if not deduped or deduped[-1] != value:
            deduped.append(value)
    return "\n".join(deduped)


def feature_flags(node: Any) -> dict[str, bool]:
    """Whether a node owns a table or figure (including table-cell nesting)."""
    found = {"has_table": False, "has_figure": False}

    def walk(current: Any) -> None:
        if isinstance(current, TableNode):
            found["has_table"] = True
            for row in [*current.headers, *current.rows]:
                for cell in row:
                    for item in cell if isinstance(cell, list) else [cell]:
                        walk(item)
        if isinstance(current, FigureNode):
            found["has_figure"] = True
        for child in getattr(current, "children", []) or []:
            walk(child)

    walk(node)
    return found
