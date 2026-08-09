"""Adapter protocol for multi-authority regulation sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class AdapterCapabilities:
    """What an adapter can do today."""

    authority: str
    fetch: bool = False
    parse: bool = False
    search: bool = False
    designations: bool = False
    notes: str = ""
    planned: list[str] = field(default_factory=list)


class RegulationAdapter(ABC):
    """Authority-specific fetch/parse bridge into the shared Regulation AST."""

    authority: str

    @abstractmethod
    def capabilities(self) -> AdapterCapabilities:
        """Describe implemented vs planned features."""

    @abstractmethod
    def list_sources(self) -> list[dict[str, Any]]:
        """Return catalog entries for this authority (may be empty)."""

    @abstractmethod
    def fetch(self, source_id: str, *, version: str | None = None) -> Path:
        """Download / resolve a source into a local package path."""

    @abstractmethod
    def parse(self, path: str | Path) -> Any:
        """Parse a local package into a ``ParseResult`` (or authority equivalent)."""

    def normalize_designation(self, text: str) -> str:
        """Optional authority-specific designation normalization."""
        return text.strip()
