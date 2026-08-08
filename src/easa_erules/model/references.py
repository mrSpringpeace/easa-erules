"""References and cross-references model."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ReferenceType(str, Enum):
    """Types of references in EASA documents."""
    INTERNAL = "internal"  # Reference to another rule in same document
    EXTERNAL = "external"  # Reference to external document
    AMC = "amc"  # Acceptable Means of Compliance reference
    GM = "gm"  # Guidance Material reference
    CS = "cs"  # Certification Specification reference
    PART = "part"  # Part reference (e.g., Part 21)
    REGULATION = "regulation"  # Regulation reference (EU regulation)
    STANDARD = "standard"  # Industry standard (ASTM, ISO, etc.)


@dataclass(slots=True)
class Reference:
    """A single reference from one element to another."""
    source_id: str  # ID of the element containing the reference
    target_id: str  # ID of the target element (if resolved)
    target_designation: str  # Human-readable designation (e.g., "CS-VLA.303")
    reference_type: ReferenceType = ReferenceType.INTERNAL
    context: str = ""  # Surrounding text context
    raw_text: str = ""  # Original reference text
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "target_designation": self.target_designation,
            "reference_type": self.reference_type.value,
            "context": self.context,
            "raw_text": self.raw_text,
            "resolved": self.resolved,
        }


@dataclass(slots=True)
class ReferenceIndex:
    """Index of all references in a document for fast lookup."""
    by_source: dict[str, list[Reference]] = field(default_factory=dict)
    by_target: dict[str, list[Reference]] = field(default_factory=dict)
    by_designation: dict[str, Reference] = field(default_factory=dict)

    def add(self, ref: Reference) -> None:
        self.by_source.setdefault(ref.source_id, []).append(ref)
        if ref.target_id:
            self.by_target.setdefault(ref.target_id, []).append(ref)
        if ref.target_designation:
            self.by_designation[ref.target_designation] = ref

    def get_references_from(self, source_id: str) -> list[Reference]:
        return self.by_source.get(source_id, [])

    def get_references_to(self, target_id: str) -> list[Reference]:
        return self.by_target.get(target_id, [])

    def resolve(self, target_designation: str) -> Reference | None:
        return self.by_designation.get(target_designation)

    def to_dict(self) -> dict[str, Any]:
        return {
            "by_source": {k: [r.to_dict() for r in v] for k, v in self.by_source.items()},
            "by_target": {k: [r.to_dict() for r in v] for k, v in self.by_target.items()},
            "by_designation": {k: v.to_dict() for k, v in self.by_designation.items()},
        }