"""Document-level model and utilities."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .. import __version__
from .node import RegulationDocument


@dataclass(slots=True)
class DocumentMetadata:
    """Metadata about the regulation document."""
    document_id: str
    title: str
    authority: str = "EASA"
    document_type: str = "certification-specification"
    version: str | None = None
    amendment: str | None = None
    publication_date: str | None = None
    source_url: str | None = None
    source_sha256: str | None = None
    parser_version: str = __version__
    parsed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")


@dataclass(slots=True)
class RegulationDocumentWrapper:
    """Wrapper for RegulationDocument with additional metadata."""
    document: RegulationDocument
    metadata: DocumentMetadata
    conversion_warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": {
                "document_id": self.metadata.document_id,
                "title": self.metadata.title,
                "authority": self.metadata.authority,
                "document_type": self.metadata.document_type,
                "version": self.metadata.version,
                "amendment": self.metadata.amendment,
                "publication_date": self.metadata.publication_date,
                "source_url": self.metadata.source_url,
                "source_sha256": self.metadata.source_sha256,
                "parser_version": self.metadata.parser_version,
                "parsed_at": self.metadata.parsed_at,
            },
            "document": self.document.to_dict(),
            "warnings": self.conversion_warnings,
        }


def create_document(
    document_id: str,
    title: str,
    authority: str = "EASA",
    version: str | None = None,
) -> RegulationDocument:
    """Factory function to create a RegulationDocument."""
    return RegulationDocument(
        title=title,
        authority=authority,
        version=version,
        document_id=document_id,
    )