"""Local cache paths for fetched EASA publications."""

from __future__ import annotations

import os
from pathlib import Path


def default_cache_root() -> Path:
    """Return the default cache root directory.

    Order:
    1. ``EASA_ERULES_CACHE`` env var
    2. ``$XDG_CACHE_HOME/easa-erules``
    3. ``~/.cache/easa-erules``
    """
    env = os.environ.get("EASA_ERULES_CACHE")
    if env:
        return Path(env).expanduser().resolve()

    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg).expanduser().resolve() / "easa-erules"

    return Path.home() / ".cache" / "easa-erules"


def document_cache_dir(document_id: str, cache_root: Path | None = None) -> Path:
    """Cache directory for a document id."""
    root = cache_root or default_cache_root()
    return root / document_id.lower()


def version_cache_dir(
    document_id: str,
    version_slug: str,
    cache_root: Path | None = None,
) -> Path:
    """Cache directory for a specific document version."""
    return document_cache_dir(document_id, cache_root) / "versions" / version_slug


def latest_pointer_path(document_id: str, cache_root: Path | None = None) -> Path:
    """Path to the ``latest`` pointer file (contains version slug)."""
    return document_cache_dir(document_id, cache_root) / "latest"
