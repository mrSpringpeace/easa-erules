"""Markdown frontmatter generator."""

from typing import Any

import yaml

from ..model import EasaMetadata, RegulationDocument, RegulationRequirement


def generate_document_frontmatter(doc: RegulationDocument, easa_meta: EasaMetadata | None = None) -> str:
    """Generate YAML frontmatter for a document."""
    frontmatter = {
        "id": doc.document_id or doc.id,
        "title": doc.title,
        "authority": doc.authority,
        "version": doc.version,
        "type": "document",
        "parser": {
            "version": "0.1.0",
        },
    }

    if easa_meta:
        frontmatter["easa"] = easa_meta.to_dict()

    return yaml.dump(frontmatter, allow_unicode=True, sort_keys=False).strip()


def generate_requirement_frontmatter(req: RegulationRequirement, easa_meta: EasaMetadata | None = None) -> str:
    """Generate YAML frontmatter for a requirement."""
    frontmatter = {
        "id": req.id,
        "rule": req.designation,
        "title": req.title,
        "type": "requirement",
        "requirement_type": req.requirement_type or "CS",
        "source": {
            "agency": "EASA",
            "document": req.metadata.get("document_id", ""),
        },
        "parser": {
            "version": "0.1.0",
        },
    }

    if easa_meta:
        frontmatter["easa"] = easa_meta.to_dict()
    elif req.metadata.get("easa"):
        frontmatter["easa"] = req.metadata["easa"]

    return yaml.dump(frontmatter, allow_unicode=True, sort_keys=False).strip()


def generate_section_frontmatter(section: Any) -> str:
    """Generate YAML frontmatter for a section."""
    frontmatter = {
        "id": section.id,
        "designation": getattr(section, 'designation', ''),
        "title": getattr(section, 'title', ''),
        "type": "section",
        "level": getattr(section, 'level', 1),
        "parser": {
            "version": "0.1.0",
        },
    }

    if section.metadata.get("easa"):
        frontmatter["easa"] = section.metadata["easa"]

    return yaml.dump(frontmatter, allow_unicode=True, sort_keys=False).strip()


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
        body = parts[2].lstrip("\n")
        return frontmatter, body
    except yaml.YAMLError:
        return {}, content