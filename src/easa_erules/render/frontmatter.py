"""Markdown frontmatter generator."""

from typing import Any

import yaml

from ..model import EasaMetadata, RegulationDocument


def _wrap(frontmatter: dict[str, Any]) -> str:
    """Serialize frontmatter as a fenced YAML block."""
    body = yaml.dump(frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False).strip()
    return f"---\n{body}\n---"


def _easa_block(easa_meta: EasaMetadata | None, fallback: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if easa_meta is not None and not easa_meta.is_empty():
        return easa_meta.to_dict()
    if fallback:
        normalized = EasaMetadata.from_dict(fallback)
        if not normalized.is_empty():
            return normalized.to_dict()
        # Keep raw fallback if model conversion emptied it
        if any(fallback.values()):
            return fallback
    return None


def generate_document_frontmatter(doc: RegulationDocument, easa_meta: EasaMetadata | None = None) -> str:
    """Generate YAML frontmatter for a document."""
    frontmatter: dict[str, Any] = {
        "id": doc.document_id or doc.id,
        "title": doc.title,
        "authority": doc.authority or "EASA",
        "version": doc.version,
        "type": "document",
        "parser": {
            "version": "0.1.0",
        },
    }

    easa = _easa_block(easa_meta, doc.metadata.get("easa") if doc.metadata else None)
    if easa:
        frontmatter["easa"] = easa

    return _wrap(frontmatter)


def generate_requirement_frontmatter(req: Any, easa_meta: EasaMetadata | None = None) -> str:
    """Generate YAML frontmatter for a requirement / AMC / GM node."""
    node_type = getattr(getattr(req, "type", None), "value", None) or "requirement"
    frontmatter: dict[str, Any] = {
        "id": getattr(req, "erules_id", "") or getattr(req, "designation", "") or req.id,
        "rule": getattr(req, "designation", "") or "",
        "title": getattr(req, "title", "") or "",
        "type": node_type,
        "requirement_type": getattr(req, "requirement_type", None) or (
            "AMC" if "amc" in node_type else "GM" if "guidance" in node_type else "CS"
        ),
        "source": {
            "agency": "EASA",
            "document": (req.metadata.get("document_id", "") if getattr(req, "metadata", None) else "") or "",
        },
        "parser": {
            "version": "0.1.0",
        },
    }

    easa = _easa_block(easa_meta, req.metadata.get("easa") if req.metadata else None)
    if easa:
        frontmatter["easa"] = easa

    return _wrap(frontmatter)


def generate_section_frontmatter(section: Any) -> str:
    """Generate YAML frontmatter for a section."""
    frontmatter: dict[str, Any] = {
        "id": getattr(section, "erules_id", "") or getattr(section, "designation", "") or section.id,
        "designation": getattr(section, "designation", ""),
        "title": getattr(section, "title", ""),
        "type": "section",
        "level": getattr(section, "level", 1),
        "parser": {
            "version": "0.1.0",
        },
    }

    easa = _easa_block(None, section.metadata.get("easa") if section.metadata else None)
    if easa:
        frontmatter["easa"] = easa

    return _wrap(frontmatter)


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
