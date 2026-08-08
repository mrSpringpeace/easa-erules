"""EASA-specific metadata model."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EasaMetadata:
    """EASA eRules specific metadata extracted from the document."""
    erules_id: str = ""
    regulatory_source: list[str] = field(default_factory=list)
    regulatory_subject: list[str] = field(default_factory=list)
    type_of_content: list[str] = field(default_factory=list)
    technical_subject_matter: list[str] = field(default_factory=list)
    aircraft_category: list[str] = field(default_factory=list)
    aircraft_use: list[str] = field(default_factory=list)
    applicability_date: str | None = None
    amended_by: list[str] = field(default_factory=list)
    source_title: str = ""

    # Raw XML attributes for preservation
    raw_attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "erules_id": self.erules_id,
            "regulatory_source": self.regulatory_source,
            "regulatory_subject": self.regulatory_subject,
            "type_of_content": self.type_of_content,
            "technical_subject_matter": self.technical_subject_matter,
            "aircraft_category": self.aircraft_category,
            "aircraft_use": self.aircraft_use,
            "applicability_date": self.applicability_date,
            "amended_by": self.amended_by,
            "source_title": self.source_title,
            "raw_attributes": self.raw_attributes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EasaMetadata":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass(slots=True)
class RequirementMetadata:
    """Metadata specific to a regulatory requirement."""
    erules_id: str = ""
    designation: str = ""
    title: str = ""
    requirement_type: str = ""  # CS, AMC, GM, etc.
    regulatory_source: list[str] = field(default_factory=list)
    regulatory_subject: list[str] = field(default_factory=list)
    type_of_content: list[str] = field(default_factory=list)
    technical_subject_matter: list[str] = field(default_factory=list)
    aircraft_category: list[str] = field(default_factory=list)
    aircraft_use: list[str] = field(default_factory=list)
    applicability_date: str | None = None
    amended_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "erules_id": self.erules_id,
            "designation": self.designation,
            "title": self.title,
            "requirement_type": self.requirement_type,
            "regulatory_source": self.regulatory_source,
            "regulatory_subject": self.regulatory_subject,
            "type_of_content": self.type_of_content,
            "technical_subject_matter": self.technical_subject_matter,
            "aircraft_category": self.aircraft_category,
            "aircraft_use": self.aircraft_use,
            "applicability_date": self.applicability_date,
            "amended_by": self.amended_by,
        }