"""Deterministic Requirement ↔ AMC/GM relationship mapping."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .model import (
    AcceptableMeansOfComplianceNode,
    GuidanceNode,
    RegulationDocument,
    RegulationRequirement,
)
from .model.references import ReferenceIndex
from .navigation import iter_topics


@dataclass(slots=True)
class RelationshipMap:
    """Associations keyed by stable ERules identity, preserving all targets."""

    nodes: dict[str, Any] = field(default_factory=dict)
    targets: dict[str, set[str]] = field(default_factory=dict)
    materials_by_requirement: dict[str, set[str]] = field(default_factory=dict)

    def related_for(self, node: Any) -> dict[str, list[dict[str, Any]]]:
        key = identity_key(node)
        requirement_keys: set[str]
        if isinstance(node, RegulationRequirement):
            requirement_keys = {key}
        else:
            requirement_keys = set(self.targets.get(key, set()))

        material_keys: set[str] = set()
        for req_key in requirement_keys:
            material_keys.update(self.materials_by_requirement.get(req_key, set()))

        requirements = [self.nodes[item] for item in requirement_keys if item in self.nodes]
        amc = [
            self.nodes[item]
            for item in material_keys
            if item in self.nodes and isinstance(self.nodes[item], AcceptableMeansOfComplianceNode)
        ]
        gm = [
            self.nodes[item]
            for item in material_keys
            if item in self.nodes and isinstance(self.nodes[item], GuidanceNode)
        ]
        return {
            "requirements": [_summary(item, self.targets.get(identity_key(item), set())) for item in _unique(requirements)],
            "amc": [_summary(item, self.targets.get(identity_key(item), set())) for item in _unique(amc)],
            "gm": [_summary(item, self.targets.get(identity_key(item), set())) for item in _unique(gm)],
        }


def build_relationship_map(
    document: RegulationDocument,
    references: ReferenceIndex | None = None,
) -> RelationshipMap:
    """Build relations from ERules metadata, designations and explicit refs."""
    result = RelationshipMap()
    topics = list(iter_topics(document))
    requirements = [node for node in topics if isinstance(node, RegulationRequirement)]
    materials = [
        node
        for node in topics
        if isinstance(node, (AcceptableMeansOfComplianceNode, GuidanceNode))
    ]
    requirements_by_norm: dict[str, str] = {}
    requirements_by_id: dict[str, str] = {}
    for requirement in requirements:
        key = identity_key(requirement)
        result.nodes.setdefault(key, requirement)
        requirements_by_norm[_normalize(getattr(requirement, "designation", ""))] = key
        if requirement.id:
            requirements_by_id[requirement.id] = key
        if getattr(requirement, "erules_id", ""):
            requirements_by_id[requirement.erules_id] = key

    for material in materials:
        key = identity_key(material)
        result.nodes.setdefault(key, material)
        target_keys: set[str] = set()
        candidates = _metadata_targets(material) + _designation_targets(material)
        for candidate in candidates:
            matched = _match_requirement(candidate, requirements_by_norm)
            if matched:
                target_keys.add(matched)
        fallback = _material_designation_match(material, requirements_by_norm)
        if fallback:
            target_keys.add(fallback)

        if references is not None:
            for ref in references.get_references_from(material.id):
                matched = requirements_by_id.get(ref.target_id)
                if matched is None:
                    matched = _match_requirement(ref.target_designation, requirements_by_norm)
                if matched:
                    target_keys.add(matched)

        # Metadata/designation/ref evidence is mandatory; physical adjacency is
        # deliberately not used as a fallback.
        result.targets.setdefault(key, set()).update(target_keys)
        for req_key in target_keys:
            result.materials_by_requirement.setdefault(req_key, set()).add(key)
    return result


def identity_key(node: Any) -> str:
    return str(getattr(node, "erules_id", "") or getattr(node, "id", ""))


def _metadata_targets(node: Any) -> list[str]:
    easa = (getattr(node, "metadata", None) or {}).get("easa") or {}
    values: list[str] = []
    for key in ("parent_ir", "parent_requirement", "related_requirements"):
        value = easa.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value:
            values.append(str(value))
    return values


def _designation_targets(node: Any) -> list[str]:
    value = f"{getattr(node, 'designation', '')} {getattr(node, 'title', '')}"
    # Handles CS-23.2100, CS 23.2100 and CS-VLA 21(c).
    found = re.findall(
        r"\bCS[\s-]*([A-Z0-9]+)[\s.-]+(\d+(?:\.\d+)?)(?:\([a-z0-9]+\))*",
        value,
        flags=re.IGNORECASE,
    )
    return [f"CS-{family}.{number}" for family, number in found]


def _match_requirement(candidate: str, index: dict[str, str]) -> str | None:
    normalized = _normalize(candidate)
    if normalized in index:
        return index[normalized]
    # parent_ir includes the title after the designation.
    for designation, key in index.items():
        if normalized.startswith(designation):
            return key
    return None


def _material_designation_match(node: Any, index: dict[str, str]) -> str | None:
    """Match legacy forms such as ``AMC VLA 21(c)`` by exact rule suffix."""
    designation = str(getattr(node, "designation", "") or "")
    match = re.search(
        r"\b(?:AMC|GM)\d*\s+([A-Z0-9-]+)\s+(\d+(?:\.\d+)?)(?:\([a-z0-9]+\))*$",
        designation,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    family, number = match.groups()
    candidate = _normalize(f"CS-{family}.{number}")
    return index.get(candidate)


def _normalize(value: str) -> str:
    value = value.replace("\xa0", " ").upper()
    value = re.sub(r"\([A-Z0-9]+\)$", "", value.strip())
    value = re.sub(r"\bCS[\s-]*([A-Z0-9]+)[\s.-]+", r"CS-\1.", value)
    return re.sub(r"[^A-Z0-9.-]", "", value)


def _summary(node: Any, target_keys: set[str]) -> dict[str, Any]:
    return {
        "id": node.id,
        "erules_id": getattr(node, "erules_id", "") or "",
        "node_type": node.type.value,
        "designation": getattr(node, "designation", "") or "",
        "title": getattr(node, "title", "") or "",
        "target_requirement_ids": sorted(target_keys),
    }


def _unique(nodes: list[Any]) -> list[Any]:
    found: dict[str, Any] = {}
    for node in nodes:
        found.setdefault(identity_key(node), node)
    return sorted(found.values(), key=lambda item: getattr(item, "designation", ""))
