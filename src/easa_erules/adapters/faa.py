"""FAA regulations adapter (scaffold).

Planned sources (not implemented):

- eCFR Title 14 (FARs), especially Part 23 / Part 25 airworthiness
- FAA Advisory Circulars where structured XML/HTML is available

The shared Regulation AST already supports multi-authority documents; this
module only needs a package reader + designation normalizer when work resumes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import AdapterCapabilities, RegulationAdapter


class FaaAdapter(RegulationAdapter):
    """Scaffold for future FAA / eCFR ingestion."""

    authority = "faa"

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            authority=self.authority,
            fetch=False,
            parse=False,
            search=False,
            designations=False,
            notes="Scaffold only. Prefer EASA designation quality before expanding.",
            planned=[
                "eCFR Title 14 package resolver",
                "FAR section designation normalizer (e.g. § 23.2000)",
                "Map AC / SFAR content into AMC/GM-like nodes where appropriate",
            ],
        )

    def list_sources(self) -> list[dict[str, Any]]:
        return []

    def fetch(self, source_id: str, *, version: str | None = None) -> Path:
        raise NotImplementedError(
            "FAA adapter is a scaffold. Use authority='easa' or implement "
            "eCFR fetch in easa_erules.adapters.faa."
        )

    def parse(self, path: str | Path) -> Any:
        raise NotImplementedError(
            "FAA adapter is a scaffold. No FAR/eCFR parser is implemented yet."
        )

    def normalize_designation(self, text: str) -> str:
        # Placeholder: strip section sign and collapse spaces
        cleaned = text.replace("§", "").strip()
        return " ".join(cleaned.split())
