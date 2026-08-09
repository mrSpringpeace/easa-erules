"""Multi-authority adapters (EASA implemented; FAA/ASTM scaffolded).

The Regulation AST is authority-agnostic. Each adapter is responsible for:

1. resolving / fetching source packages for that authority,
2. parsing into the shared AST,
3. optional authority-specific designation normalization.

Only the EASA adapter is production-ready. FAA and ASTM modules define the
extension points and raise ``NotImplementedError`` until packages are available.
"""

from .astm import AstmAdapter
from .base import AdapterCapabilities, RegulationAdapter
from .easa import EasaAdapter
from .faa import FaaAdapter

__all__ = [
    "AdapterCapabilities",
    "AstmAdapter",
    "EasaAdapter",
    "FaaAdapter",
    "RegulationAdapter",
    "get_adapter",
]


def get_adapter(authority: str) -> RegulationAdapter:
    """Return an adapter instance for ``authority`` (easa / faa / astm)."""
    key = (authority or "").strip().lower()
    mapping: dict[str, type[RegulationAdapter]] = {
        "easa": EasaAdapter,
        "faa": FaaAdapter,
        "astm": AstmAdapter,
    }
    try:
        cls = mapping[key]
    except KeyError as exc:
        raise ValueError(
            f"Unknown authority {authority!r}. Known: {', '.join(sorted(mapping))}"
        ) from exc
    return cls()
