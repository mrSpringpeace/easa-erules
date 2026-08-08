"""Reference graph utilities (outgoing / incoming edges)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .node import (
    AcceptableMeansOfComplianceNode,
    GuidanceNode,
    InternalReferenceNode,
    RegulationDocument,
    RegulationRequirement,
    RegulationSection,
)


@dataclass(slots=True)
class RefEdge:
    source_designation: str
    source_id: str
    target_designation: str
    target_id: str
    raw_text: str
    resolved: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_designation": self.source_designation,
            "source_id": self.source_id,
            "target_designation": self.target_designation,
            "target_id": self.target_id,
            "raw_text": self.raw_text,
            "resolved": self.resolved,
        }


@dataclass(slots=True)
class RefNodeGraph:
    designation: str
    node_id: str
    title: str
    references: list[RefEdge] = field(default_factory=list)
    referenced_by: list[RefEdge] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "designation": self.designation,
            "id": self.node_id,
            "title": self.title,
            "references": [e.to_dict() for e in self.references],
            "referenced_by": [e.to_dict() for e in self.referenced_by],
        }

    def to_text_tree(self) -> str:
        lines = [self.designation or self.node_id]
        if self.references:
            lines.append("├── references → " + ", ".join(
                e.target_designation or e.target_id for e in self.references
            ))
        else:
            lines.append("├── references → (none)")
        if self.referenced_by:
            lines.append("└── referenced-by → " + ", ".join(
                e.source_designation or e.source_id for e in self.referenced_by
            ))
        else:
            lines.append("└── referenced-by → (none)")
        return "\n".join(lines)


def build_reference_graph(doc: RegulationDocument) -> dict[str, RefNodeGraph]:
    """Build designation → RefNodeGraph for all topics in the document."""
    topics: dict[str, RefNodeGraph] = {}
    by_id: dict[str, RefNodeGraph] = {}
    edges: list[RefEdge] = []

    def register_topic(node: Any) -> RefNodeGraph:
        des = getattr(node, "designation", "") or getattr(node, "erules_id", "") or node.id
        g = RefNodeGraph(
            designation=getattr(node, "designation", "") or des,
            node_id=node.id or des,
            title=getattr(node, "title", "") or "",
        )
        topics[g.designation] = g
        if g.node_id:
            by_id[g.node_id] = g
        erules = getattr(node, "erules_id", "") or ""
        if erules and erules not in topics:
            topics[erules] = g
        return g

    def walk(node: Any, current_topic: RefNodeGraph | None) -> None:
        if isinstance(
            node,
            (
                RegulationRequirement,
                GuidanceNode,
                AcceptableMeansOfComplianceNode,
                RegulationSection,
            ),
        ):
            current_topic = register_topic(node)

        if isinstance(node, InternalReferenceNode) and current_topic is not None:
            edges.append(
                RefEdge(
                    source_designation=current_topic.designation,
                    source_id=current_topic.node_id,
                    target_designation=node.target_designation or "",
                    target_id=node.target_id or "",
                    raw_text=node.text or node.target_designation or "",
                    resolved=bool(node.target_id),
                )
            )

        for child in getattr(node, "children", []) or []:
            walk(child, current_topic)

    walk(doc, None)

    for edge in edges:
        src = topics.get(edge.source_designation) or by_id.get(edge.source_id)
        if src:
            src.references.append(edge)
        tgt = None
        if edge.target_designation:
            tgt = topics.get(edge.target_designation)
        if tgt is None and edge.target_id:
            tgt = by_id.get(edge.target_id)
        if tgt:
            tgt.referenced_by.append(edge)

    return topics


def lookup_refs(doc: RegulationDocument, designation: str) -> RefNodeGraph | None:
    """Return the reference graph node for a designation (case-insensitive)."""
    graph = build_reference_graph(doc)
    if designation in graph:
        return graph[designation]
    needle = designation.replace(" ", "-").upper()
    for key, node in graph.items():
        if key.replace(" ", "-").upper() == needle:
            return node
        if node.node_id.replace(" ", "-").upper() == needle:
            return node
    return None
