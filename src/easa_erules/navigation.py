"""Deterministic outline and source-order navigation for flat EASA ASTs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from .model import (
    AcceptableMeansOfComplianceNode,
    GuidanceNode,
    RegulationDocument,
    RegulationRequirement,
    RegulationSection,
)

TOPIC_TYPES = (
    RegulationRequirement,
    GuidanceNode,
    AcceptableMeansOfComplianceNode,
)


@dataclass(slots=True)
class NavigationIndex:
    """Outline plus lookup metadata used by context and search."""

    outline: list[dict[str, Any]] = field(default_factory=list)
    breadcrumb_by_id: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    ancestors_by_id: dict[str, list[str]] = field(default_factory=dict)
    structure_kind_by_id: dict[str, str] = field(default_factory=dict)
    node_by_id: dict[str, Any] = field(default_factory=dict)
    navigable: list[Any] = field(default_factory=list)


def build_navigation(document: RegulationDocument) -> NavigationIndex:
    """Build a hierarchy from ordered sections and their levels."""
    index = NavigationIndex()
    stack: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
    ordinal = 0
    front: dict[str, Any] | None = None

    def section_path() -> list[dict[str, Any]]:
        return [entry for _, entry, _ in stack]

    def add_section(node: RegulationSection) -> None:
        nonlocal ordinal
        ordinal += 1
        kind = classify_structure(node)
        level = structure_level(node, kind)
        while stack and stack[-1][0] >= level:
            stack.pop()
        entry: dict[str, Any] = {
            "id": node.id,
            "kind": kind,
            "node_type": node.type.value,
            "designation": node.designation,
            "title": node.title,
            "level": level,
            "ordinal": ordinal,
            "navigable": False,
            "children": [],
        }
        parent_children = stack[-1][1]["children"] if stack else index.outline
        parent_children.append(entry)
        path = section_path() + [entry]
        crumbs = [_crumb(item) for item in path]
        ancestors = [item["id"] for item in path if item["id"]]
        index.node_by_id[node.id] = node
        index.breadcrumb_by_id[node.id] = crumbs
        index.ancestors_by_id[node.id] = ancestors[:-1]
        index.structure_kind_by_id[node.id] = kind
        stack.append((level, entry, crumbs))

    def ensure_front() -> dict[str, Any]:
        nonlocal front, ordinal
        if front is None:
            ordinal += 1
            front = {
                "id": "front-matter",
                "kind": "front_matter",
                "node_type": "section",
                "designation": "",
                "title": "Front matter",
                "level": 1,
                "ordinal": ordinal,
                "navigable": False,
                "children": [],
            }
            index.outline.append(front)
        return front

    def add_topic(node: Any) -> None:
        nonlocal ordinal
        ordinal += 1
        if stack:
            parent = stack[-1][1]
            path = section_path()
            kind = parent["kind"]
        else:
            parent = ensure_front()
            path = [parent]
            kind = "front_matter"
        entry = {
            "id": node.id,
            "kind": kind,
            "node_type": node.type.value,
            "designation": getattr(node, "designation", "") or "",
            "title": getattr(node, "title", "") or "",
            "level": (path[-1]["level"] + 1) if path else 1,
            "ordinal": ordinal,
            "navigable": True,
            "children": [],
        }
        parent["children"].append(entry)
        index.node_by_id[node.id] = node
        index.navigable.append(node)
        index.breadcrumb_by_id[node.id] = [_crumb(item) for item in [*path, entry]]
        index.ancestors_by_id[node.id] = [item["id"] for item in path if item["id"]]
        index.structure_kind_by_id[node.id] = kind

    def process(node: Any) -> None:
        if isinstance(node, RegulationSection):
            add_section(node)
            for child in node.children:
                process(child)
            return
        if isinstance(node, TOPIC_TYPES):
            add_topic(node)
            # Nested formatting is not part of the outline, but a malformed
            # source may contain nested topics and they remain navigable.
            for child in node.children:
                if isinstance(child, (RegulationSection, *TOPIC_TYPES)):
                    process(child)
            return
        for child in getattr(node, "children", []) or []:
            if isinstance(child, (RegulationSection, *TOPIC_TYPES)):
                process(child)

    for child in document.children:
        process(child)
    return index


def classify_structure(section: RegulationSection) -> str:
    """Classify structural headings from source designation/metadata/title."""
    designation = (section.designation or "").strip()
    title = (section.title or "").strip()
    text = f"{designation} {title}".strip()
    easa = (section.metadata or {}).get("easa") or {}
    types = " ".join(str(v) for v in easa.get("type_of_content", [])).lower()
    normalized = " ".join(text.lower().split())
    if "definition" in types or re.search(r"\bdefinitions?\b", normalized):
        return "definitions"
    if "appendix" in types or re.match(r"^(appendix|appendices)\b", normalized):
        return "appendix"
    if re.match(r"^book\b", normalized):
        return "book"
    if re.match(r"^part\b", normalized):
        return "part"
    if re.match(r"^subpart\b", normalized):
        return "subpart"
    if re.match(r"^chapter\b", normalized):
        return "chapter"
    if normalized in {
        "disclaimer",
        "note from the editor",
        "incorporated amendments",
        "preamble",
    } or normalized.startswith("toc "):
        return "front_matter"
    return "section"


def structure_level(section: RegulationSection, kind: str) -> int:
    """Stable hierarchy level, preferring meaningful parser levels."""
    source_level = max(1, int(section.level or 1))
    if source_level > 1:
        return source_level
    return {
        "front_matter": 1,
        "part": 1,
        "book": 1,
        "appendix": 1,
        "subpart": 2,
        "definitions": 2,
        "chapter": 3,
        "section": 3,
    }.get(kind, 3)


def iter_topics(document: RegulationDocument) -> Iterator[Any]:
    """Yield navigable topics in source order."""
    yield from build_navigation(document).navigable


def _crumb(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "kind": item["kind"],
        "node_type": item["node_type"],
        "designation": item["designation"],
        "title": item["title"],
    }
