"""Deterministic ID assignment for AST nodes."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..model import (
    AcceptableMeansOfComplianceNode,
    GuidanceNode,
    Node,
    RegulationDocument,
    RegulationRequirement,
    RegulationSection,
)
from .slugify import slugify, slugify_rule


def stable_node_id(*parts: str) -> str:
    """Build a stable, filesystem-friendly node id from parts."""
    cleaned = [slugify(p) if p else "" for p in parts]
    cleaned = [p for p in cleaned if p]
    return "-".join(cleaned) if cleaned else "node"


def assign_deterministic_ids(root: Node) -> None:
    """Assign deterministic IDs to all nodes in the tree (in-place).

    Preference order:
    1. document_id / erules_id / designation
    2. Path-based sequential IDs under the parent (stable across re-parses)
    """
    counters: dict[str, int] = defaultdict(int)

    def walk(node: Node, parent_id: str) -> None:
        explicit = _explicit_id(node)
        if explicit:
            node.id = explicit
        else:
            kind = node.type.value if node.type else "node"
            counters[kind] += 1
            suffix = f"{kind}-{counters[kind]:04d}"
            node.id = f"{parent_id}/{suffix}" if parent_id else suffix

        for child in node.children:
            walk(child, node.id)

    walk(root, "")


def _explicit_id(node: Node) -> str:
    if isinstance(node, RegulationDocument) and node.document_id:
        return node.document_id
    if isinstance(
        node,
        (RegulationRequirement, GuidanceNode, AcceptableMeansOfComplianceNode),
    ):
        if node.erules_id:
            return node.erules_id
        if node.designation:
            return node.designation
    if isinstance(node, RegulationSection):
        if node.designation:
            return node.designation
        if node.title:
            return stable_node_id("section", node.title)
    return ""


def rule_file_slug(node: Any) -> str:
    """Filename slug for a rule/section node (without extension)."""
    designation = getattr(node, "designation", "") or getattr(node, "erules_id", "") or ""
    if designation:
        return slugify_rule(designation)
    title = getattr(node, "title", "") or getattr(node, "id", "rule")
    return slugify(title)
