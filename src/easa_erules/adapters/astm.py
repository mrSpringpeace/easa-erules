"""ASTM consensus standards adapter (scaffold).

Planned sources (not implemented):

- ASTM F44 (Normal Category Aeroplanes) consensus standards referenced from
  CS-23 AMC / GM tables
- Other ASTM committees cited by EASA AMC material

ASTM documents are typically PDF/HTML under license; any future adapter must
respect ASTM redistribution terms and prefer official structured exports if
they become available.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import AdapterCapabilities, RegulationAdapter


class AstmAdapter(RegulationAdapter):
    """Scaffold for future ASTM standard ingestion."""

    authority = "astm"

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            authority=self.authority,
            fetch=False,
            parse=False,
            search=False,
            designations=False,
            notes=(
                "Scaffold only. Licensing and package format TBD. "
                "Cross-refs from CS-23 AMC already surface ASTM designations via EASA parser."
            ),
            planned=[
                "Catalog of F44 standards referenced by CS-23 AMC",
                "Designation normalizer (e.g. ASTM F3264-…)",
                "Optional local PDF/HTML extract under license compliance",
            ],
        )

    def list_sources(self) -> list[dict[str, Any]]:
        return []

    def fetch(self, source_id: str, *, version: str | None = None) -> Path:
        raise NotImplementedError(
            "ASTM adapter is a scaffold. Licensing and fetch are not implemented."
        )

    def parse(self, path: str | Path) -> Any:
        raise NotImplementedError(
            "ASTM adapter is a scaffold. No ASTM package parser is implemented yet."
        )

    def normalize_designation(self, text: str) -> str:
        cleaned = text.strip()
        # ASTM F3264-17 → ASTM F3264-17
        return " ".join(cleaned.split())
