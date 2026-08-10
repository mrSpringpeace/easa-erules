"""Multi-authority adapters.

The Regulation AST is authority-agnostic. Each adapter is responsible for:

1. resolving / fetching source packages for that authority,
2. parsing into the shared AST,
3. optional authority-specific designation normalization.

EASA is production. FAA (14 CFR via the public eCFR API) is a working
prototype. ASTM is deliberately absent: those standards are paywalled and
cannot be redistributed, so there is nothing for an adapter to fetch.
"""

from .base import AdapterCapabilities, RegulationAdapter
from .easa import EasaAdapter
from .faa import FaaAdapter, FaaEcfrAdapter

__all__ = [
    "AdapterCapabilities",
    "EasaAdapter",
    "FaaAdapter",
    "FaaEcfrAdapter",
    "RegulationAdapter",
    "get_adapter",
]


def get_adapter(authority: str) -> RegulationAdapter:
    """Return an adapter instance for ``authority`` (easa / faa)."""
    key = (authority or "").strip().lower()
    mapping: dict[str, type[RegulationAdapter]] = {
        "easa": EasaAdapter,
        "faa": FaaEcfrAdapter,
    }
    try:
        cls = mapping[key]
    except KeyError as exc:
        raise ValueError(
            f"Unknown authority {authority!r}. Known: {', '.join(sorted(mapping))}"
        ) from exc
    return cls()
