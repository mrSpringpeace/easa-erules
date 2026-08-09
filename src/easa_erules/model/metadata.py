"""EASA-specific metadata model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Map EASA XML local names (camelCase / PascalCase export attrs) to model fields.
_XML_FIELD_MAP: dict[str, str] = {
    "erules_id": "erules_id",
    "id": "erules_id",
    "ERulesId": "erules_id",
    "regulatory_source": "regulatory_source",
    "regulatorySource": "regulatory_source",
    "RegulatorySource": "regulatory_source",
    "regulatory_subject": "regulatory_subject",
    "regulatorySubject": "regulatory_subject",
    "RegulatorySubject": "regulatory_subject",
    "type_of_content": "type_of_content",
    "typeOfContent": "type_of_content",
    "TypeOfContent": "type_of_content",
    "technical_subject_matter": "technical_subject_matter",
    "technicalSubjectMatter": "technical_subject_matter",
    "TechnicalSubjectMatter": "technical_subject_matter",
    "aircraft_category": "aircraft_category",
    "aircraftCategory": "aircraft_category",
    "AircraftCategory": "aircraft_category",
    "aircraft_use": "aircraft_use",
    "aircraftUse": "aircraft_use",
    "AircraftUse": "aircraft_use",
    "applicability_date": "applicability_date",
    "applicabilityDate": "applicability_date",
    "ApplicabilityDate": "applicability_date",
    "amended_by": "amended_by",
    "amendedBy": "amended_by",
    "AmendedBy": "amended_by",
    "source_title": "source_title",
    "title": "source_title",
    "sourceTitle": "source_title",
    "source-title": "source_title",
    # Extended export / SDT fields
    "domain": "domain",
    "Domain": "domain",
    "parent_ir": "parent_ir",
    "ParentIR": "parent_ir",
    "entry_into_force_date": "entry_into_force_date",
    "EntryIntoForceDate": "entry_into_force_date",
    "keywords": "keywords",
    "Keywords": "keywords",
    "sdt_id": "sdt_id",
    "sdt-id": "sdt_id",
    "easa_category": "easa_category",
    "EASACategory": "easa_category",
    "activity_type": "activity_type",
    "ActivityType": "activity_type",
    "equivalent_foreign_regulation": "equivalent_foreign_regulation",
    "EquivalentForeignRegulation": "equivalent_foreign_regulation",
    "icao_reference": "icao_reference",
    "ICAOReference": "icao_reference",
    "registry_state": "registry_state",
    "RegistryState": "registry_state",
    "regulated_entity": "regulated_entity",
    "RegulatedEntity": "regulated_entity",
    "guid": "guid",
    "pub_time": "pub_time",
    "pub-time": "pub_time",
}

_LIST_FIELDS = {
    "regulatory_source",
    "regulatory_subject",
    "type_of_content",
    "technical_subject_matter",
    "aircraft_category",
    "aircraft_use",
    "amended_by",
    "keywords",
}

# Values that export packages use as empty placeholders
_EMPTY_SENTINELS = {"", "n/a", "n/a;", "na", "-"}


def _split_semi(value: Any) -> list[str]:
    """Split semicolon-separated export attribute values into clean items."""
    if value is None:
        return []
    if isinstance(value, list):
        items: list[str] = []
        for v in value:
            items.extend(_split_semi(v))
        return items
    text = str(value).strip()
    if text.lower() in _EMPTY_SENTINELS:
        return []
    parts = [p.strip() for p in text.split(";")]
    return [p for p in parts if p and p.lower() not in _EMPTY_SENTINELS]


def _scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
        if value is None:
            return None
    text = str(value).strip()
    if not text or text.lower() in _EMPTY_SENTINELS:
        return None
    # Strip trailing semicolon used in export packages
    if text.endswith(";"):
        text = text[:-1].strip()
    return text or None


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
            items = _split_semi(value)
            existing = result.get(field_name)
            if existing:
                # de-dupe while preserving order
                seen = set(existing)
                merged = list(existing)
                for item in items:
                    if item not in seen:
                        merged.append(item)
                        seen.add(item)
                result[field_name] = merged
            else:
                result[field_name] = items
        else:
            cleaned = _scalar(value)
            if cleaned is not None:
                result[field_name] = cleaned

    if raw:
        result["raw_attributes"] = raw
    return result


@dataclass(slots=True)
class EasaMetadata:
    """EASA eRules specific metadata extracted from the document or export package."""

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
    # Extended fields from official erules-export customXml / core props
    domain: str = ""
    parent_ir: str = ""
    entry_into_force_date: str | None = None
    keywords: list[str] = field(default_factory=list)
    sdt_id: str = ""
    easa_category: str = ""
    activity_type: str = ""
    equivalent_foreign_regulation: str = ""
    icao_reference: str = ""
    registry_state: str = ""
    regulated_entity: str = ""
    guid: str = ""
    pub_time: str = ""

    # Raw XML attributes for preservation
    raw_attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # Core fields always present (stable JSON / frontmatter shape).
        result: dict[str, Any] = {
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
        # Extended export/SDT fields only when populated (keeps fixtures compact).
        extended = {
            "domain": self.domain,
            "parent_ir": self.parent_ir,
            "entry_into_force_date": self.entry_into_force_date,
            "keywords": self.keywords,
            "sdt_id": self.sdt_id,
            "easa_category": self.easa_category,
            "activity_type": self.activity_type,
            "equivalent_foreign_regulation": self.equivalent_foreign_regulation,
            "icao_reference": self.icao_reference,
            "registry_state": self.registry_state,
            "regulated_entity": self.regulated_entity,
            "guid": self.guid,
            "pub_time": self.pub_time,
        }
        for key, value in extended.items():
            if value is None or value == "" or value == []:
                continue
            result[key] = value
        return result


    def is_empty(self) -> bool:
        """Return True if no meaningful metadata fields are set."""
        return not any(
            [
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
                self.domain,
                self.parent_ir,
                self.entry_into_force_date,
                self.keywords,
                self.sdt_id,
                self.guid,
                self.pub_time,
            ]
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EasaMetadata:
        normalized = normalize_easa_metadata_dict(data)
        fields = cls.__dataclass_fields__
        kwargs: dict[str, Any] = {}
        for k, v in normalized.items():
            if k not in fields:
                continue
            if k in _LIST_FIELDS and v is None:
                kwargs[k] = []
            else:
                kwargs[k] = v
        return cls(**kwargs)


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
    parent_ir: str = ""
    domain: str = ""
    sdt_id: str = ""

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
            "parent_ir": self.parent_ir,
            "domain": self.domain,
            "sdt_id": self.sdt_id,
        }
