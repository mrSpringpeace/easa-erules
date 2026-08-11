"""Local cache paths for fetched EASA publications."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any


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


_SAFE_VERSION_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")


def delete_version_directory(
    document_id: str,
    version_slug: str,
    *,
    cache_root: Path | None = None,
) -> dict[str, Any]:
    """Delete exactly one safe version directory and repair latest pointers."""
    if not _SAFE_VERSION_SLUG.fullmatch(version_slug) or version_slug in {".", ".."}:
        raise ValueError("version_slug must be an exact safe cache slug")

    root = (cache_root or default_cache_root()).resolve()
    doc_dir = document_cache_dir(document_id, root)
    resolved_doc = doc_dir.resolve()
    if resolved_doc.parent != root:
        raise ValueError("document cache resolves outside the configured cache root")
    versions_root = doc_dir / "versions"
    target = versions_root / version_slug
    if target.is_symlink() or not target.is_dir():
        raise FileNotFoundError(f"Cached version not found: {document_id}/{version_slug}")

    resolved_root = versions_root.resolve()
    resolved_target = target.resolve()
    if resolved_target.parent != resolved_root:
        raise ValueError("cached version resolves outside the document cache")

    logical_artifacts = [f"versions/{version_slug}"]
    pointer = latest_pointer_path(document_id, cache_root)
    pointed = ""
    try:
        if pointer.is_file():
            pointed = pointer.read_text(encoding="utf-8").strip()
    except OSError:
        pointed = ""

    shutil.rmtree(resolved_target)

    if pointed == version_slug:
        from .inventory import list_cached_version_records

        remaining = list_cached_version_records(document_id, cache_root=cache_root)
        root_source = doc_dir / "source.xml"
        root_meta = doc_dir / "meta.yaml"
        if remaining and remaining[0].source_path.is_file():
            latest = remaining[0]
            pointer.write_text(latest.version_slug + "\n", encoding="utf-8")
            shutil.copyfile(latest.source_path, root_source)
            latest_meta = latest.source_path.with_name("meta.yaml")
            if latest_meta.is_file():
                shutil.copyfile(latest_meta, root_meta)
            elif root_meta.exists():
                root_meta.unlink()
            logical_artifacts.append("latest_pointer_reassigned")
        else:
            for path in (pointer, root_source, root_meta):
                if path.exists() or path.is_symlink():
                    path.unlink()
            logical_artifacts.append("latest_pointer_removed")

    return {
        "document_id": document_id,
        "version_slug": version_slug,
        "removed": logical_artifacts,
    }
