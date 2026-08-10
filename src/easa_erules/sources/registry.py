"""EASA Sources Registry — loads built-in easa.yaml catalog."""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

_REGISTRY_FILENAME = "easa.yaml"
#: Catalogs merged into the registry, in order. Later files may not override
#: earlier ids — a collision is a packaging bug, not a precedence rule.
_CATALOG_FILENAMES = ("easa.yaml", "faa.yaml")


def _catalog_path(filename: str) -> Path:
    """Locate a packaged catalog file (editable install or wheel)."""
    try:
        ref = resources.files("easa_erules.sources").joinpath(filename)
        with resources.as_file(ref) as path:
            return Path(path)
    except (FileNotFoundError, ModuleNotFoundError, TypeError, AttributeError):
        return Path(__file__).with_name(filename)


def _default_registry_path() -> Path:
    """Locate packaged easa.yaml (editable install or wheel)."""
    return _catalog_path(_REGISTRY_FILENAME)


def _read_catalog(reg_path: Path) -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
    sources = data.get("sources") or data
    if not isinstance(sources, dict):
        raise ValueError(f"Invalid registry format in {reg_path}")
    return {str(k).lower(): dict(v) for k, v in sources.items()}


@lru_cache(maxsize=4)
def load_registry(path: str | None = None) -> dict[str, dict[str, Any]]:
    """Load the sources catalog.

    Returns mapping of canonical id → source dict (without the outer ``sources``
    key). With no explicit *path*, every packaged catalog is merged so FAA and
    EASA documents share one id space.
    """
    if path:
        return _read_catalog(Path(path))

    merged: dict[str, dict[str, Any]] = {}
    for filename in _CATALOG_FILENAMES:
        catalog_path = _catalog_path(filename)
        if not catalog_path.is_file():
            continue
        for key, value in _read_catalog(catalog_path).items():
            if key in merged:
                raise ValueError(f"Duplicate source id {key!r} in {filename}")
            merged[key] = value
    return merged


def clear_registry_cache() -> None:
    """Clear cached registry (for tests)."""
    load_registry.cache_clear()


def _registry() -> dict[str, dict[str, Any]]:
    return load_registry()


class _RegistryView:
    """Dict-like view over the loaded registry (always current after cache clear)."""

    def __getitem__(self, key: str) -> dict[str, Any]:
        return _registry()[key]

    def __iter__(self):
        return iter(_registry())

    def __len__(self) -> int:
        return len(_registry())

    def __contains__(self, key: object) -> bool:
        return key in _registry()

    def items(self):
        return _registry().items()

    def keys(self):
        return _registry().keys()

    def values(self):
        return _registry().values()

    def get(self, key: str, default: Any = None) -> Any:
        return _registry().get(key, default)

    def __repr__(self) -> str:
        return f"REGISTRY({_registry()!r})"


REGISTRY = _RegistryView()


def resolve_source_id(doc_id: str) -> str:
    """Resolve a document ID or alias to the canonical registry key."""
    key = doc_id.lower().strip()
    reg = _registry()
    if key in reg:
        return key

    for registry_key, source in reg.items():
        for alias in source.get("aliases", []) or []:
            if str(alias).lower() == key:
                return registry_key

    raise KeyError(f"Unknown source: {doc_id}")


def get_source(doc_id: str) -> dict[str, Any]:
    """Get source by ID or alias. Includes canonical ``id`` field."""
    key = resolve_source_id(doc_id)
    return {"id": key, **_registry()[key]}


def list_sources() -> list[dict[str, Any]]:
    """List all available sources."""
    return [{"id": k, **v} for k, v in _registry().items()]
