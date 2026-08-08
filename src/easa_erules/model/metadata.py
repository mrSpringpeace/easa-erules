"""EASA-specific metadata model."""

from dataclasses import dataclass, field
from typing import Any

# Map EASA XML local names (camelCase) and variants to model field names.
_XML_FIELD_MAP: dict[str, str] = {
    "erules_id": "erules_id",
    "id": "erules_id",
    "ERulesId": "erules_id",
    "regulatory_source": "regulatory_source",
    "regulatorySource": "regulatory_source",
    "regulatory_subject": "regulatory_subject",
    "regulatorySubject": "regulatory_subject",
    "type_of_content": "type_of_content",
    "typeOfContent": "type_of_content",
    "technical_subject_matter": "technical_subject_matter",
    "technicalSubjectMatter": "technical_subject_matter",
    "aircraft_category": "aircraft_category",
    "aircraftCategory": "aircraft_category",
    "aircraft_use": "aircraft_use",
    "aircraftUse": "aircraft_use",
    "applicability_date": "applicability_date",
    "applicabilityDate": "applicability_date",
    "amended_by": "amended_by",
    "amendedBy": "amended_by",
    "source_title": "source_title",
    "title": "source_title",
    "sourceTitle": "source_title",
}

_LIST_FIELDS = {
    "regulatory_source",
    "regulatory_subject",
    "type_of_content",
    "technical_subject_matter",
    "aircraft_category",
    "aircraft_use",
    "amended_by",
}


def normalize_easa_metadata_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize camelCase / mixed EASA metadata keys to model field names."""
    if not data:
        return {}

    result: dict[str, Any] = {}
    raw: dict[str, Any] = {}

    for key, value in data.items():
        if key == "raw_attributes" and isinstance(value, dict):
            raw.update(value)
            continue

        field_name = _XML_FIELD_MAP.get(key)
        if field_name is None:
            raw[key] = value
            continue

        if field_name in _LIST_FIELDS:
            if isinstance(value, list):
                items = list(value)
            elif value is None or value == "":
                items = []
            else:
                items = [value]
            existing = result.get(field_name)
            if existing:
                result[field_name] = list(existing) + items
            else:
                result[field_name] = items
        else:
            result[field_name] = value

    if raw:
        result["raw_attributes"] = raw
    return result


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

    def is_empty(self) -> bool:
        """Return True if no meaningful metadata fields are set."""
        return not any([
            self.erules_id,
            self.regulatory_source,
            self.regulatory_subject,
            self.type_of_content,
            self.technical_subject_matter,
            self.aircraft_category,
            self.aircraft_use,
            self.applicability_date,
            self.amended_by,
            self.source_title,
        ])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EasaMetadata":
        normalized = normalize_easa_metadata_dict(data)
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in normalized.items() if k in fields})


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