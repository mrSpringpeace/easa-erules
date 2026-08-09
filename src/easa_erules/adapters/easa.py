"""EASA Easy Access Rules adapter (production path)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..input.package import OpcPackage
from ..parser import EasaDocumentParser
from ..sources.registry import list_sources as registry_list
from ..util.slugify import normalize_designation
from .base import AdapterCapabilities, RegulationAdapter


class EasaAdapter(RegulationAdapter):
    """Full EASA pipeline: registry + fetch + Flat OPC/SDT parse → AST."""

    authority = "easa"

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            authority=self.authority,
            fetch=True,
            parse=True,
            search=True,
            designations=True,
            notes="Production adapter for EASA Easy Access Rules XML exports.",
            planned=[],
        )

    def list_sources(self) -> list[dict[str, Any]]:
        return list(registry_list())

    def fetch(self, source_id: str, *, version: str | None = None) -> Path:
        from ..sources import EasaDownloader

        with EasaDownloader() as dl:
            fetched = dl.fetch(source_id, version=version)
        return Path(fetched.source_path)

    def parse(self, path: str | Path) -> Any:
        package = OpcPackage.from_file(path)
        return EasaDocumentParser(package).parse()

    def normalize_designation(self, text: str) -> str:
        return normalize_designation(text)
