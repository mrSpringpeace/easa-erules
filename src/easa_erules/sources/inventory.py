"""Safe, network-free inventory of cached regulation versions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .cache import document_cache_dir, latest_pointer_path

INTEGRITY_STATES = {
    "unchecked",
    "ok",
    "mismatch",
    "metadata_missing",
    "metadata_unreadable",
    "source_missing",
}


def sha256_file(path: Path) -> str:
    """Return a streaming SHA-256 for *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(slots=True)
class CachedVersion:
    """One version directory in the local cache."""

    version_label: str
    version_slug: str
    retrieved_at: str
    source_path: Path
    size: int | None
    sha256: str | None
    is_latest_pointer: bool
    integrity_state: str
    actual_sha256: str | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_label": self.version_label,
            "version_slug": self.version_slug,
            "retrieved_at": self.retrieved_at,
            "source_path": str(self.source_path),
            "size": self.size,
            "sha256": self.sha256,
            "is_latest_pointer": self.is_latest_pointer,
            "integrity": {
                "state": self.integrity_state,
                "expected_sha256": self.sha256,
                "actual_sha256": self.actual_sha256,
            },
        }


def list_cached_version_records(
    document_id: str,
    *,
    cache_root: Path | None = None,
    verify_integrity: bool = False,
) -> list[CachedVersion]:
    """List version directories without consulting the network.

    Broken metadata and missing source files are represented as explicit
    inventory states rather than causing the entire inventory to fail.
    """
    doc_dir = document_cache_dir(document_id, cache_root)
    versions_root = doc_dir / "versions"
    if not versions_root.is_dir():
        return []

    latest_slug = ""
    pointer = latest_pointer_path(document_id, cache_root)
    try:
        if pointer.is_file():
            latest_slug = pointer.read_text(encoding="utf-8").strip()
    except OSError:
        latest_slug = ""

    versions: list[CachedVersion] = []
    for version_dir in versions_root.iterdir():
        # A symlink is never followed while taking inventory. Cache versions
        # created by the downloader are real directories.
        if not version_dir.is_dir() or version_dir.is_symlink():
            continue
        slug = version_dir.name
        source_path = version_dir / "source.xml"
        meta_path = version_dir / "meta.yaml"
        meta: dict[str, Any] | None = None
        metadata_state = "unchecked"
        if not meta_path.exists():
            metadata_state = "metadata_missing"
        else:
            try:
                loaded = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    raise ValueError("metadata root is not a mapping")
                meta = loaded
            except (OSError, UnicodeError, yaml.YAMLError, ValueError):
                metadata_state = "metadata_unreadable"

        version_meta = (meta or {}).get("version") or {}
        integrity_meta = (meta or {}).get("integrity") or {}
        expected = integrity_meta.get("sha256")
        expected = str(expected) if expected else None
        declared_size = integrity_meta.get("size")
        try:
            size = int(declared_size) if declared_size is not None else None
        except (TypeError, ValueError):
            size = None

        actual: str | None = None
        if not source_path.is_file():
            state = "source_missing"
        elif metadata_state != "unchecked":
            state = metadata_state
            if size is None:
                size = source_path.stat().st_size
        elif not expected:
            state = "metadata_missing"
            if size is None:
                size = source_path.stat().st_size
        elif verify_integrity:
            actual = sha256_file(source_path)
            state = "ok" if actual == expected else "mismatch"
            if size is None:
                size = source_path.stat().st_size
        else:
            state = "unchecked"
            if size is None:
                size = source_path.stat().st_size

        versions.append(
            CachedVersion(
                version_label=str(version_meta.get("label") or slug),
                # The directory name is the authoritative cache key. Metadata
                # may be damaged or stale and must not redirect cache access.
                version_slug=slug,
                retrieved_at=str((meta or {}).get("retrieved_at") or ""),
                source_path=source_path,
                size=size,
                sha256=expected,
                is_latest_pointer=slug == latest_slug,
                integrity_state=state,
                actual_sha256=actual,
                metadata=meta,
            )
        )

    versions.sort(key=lambda item: _version_sort_key(item.version_slug), reverse=True)
    return versions


def resolve_cached_version(
    document_id: str,
    version: str,
    *,
    cache_root: Path | None = None,
    verify_integrity: bool = False,
) -> CachedVersion | None:
    """Resolve only an exact slug or exact normalized version label."""
    needle = _normalize_version(version)
    matches = [
        item
        for item in list_cached_version_records(
            document_id,
            cache_root=cache_root,
            verify_integrity=verify_integrity,
        )
        if item.version_slug == version
        or _normalize_version(item.version_slug) == needle
        or _normalize_version(item.version_label) == needle
    ]
    return matches[0] if len(matches) == 1 else None


def _normalize_version(value: str) -> str:
    value = value.strip().lower().replace("&", " and ")
    value = re.sub(r"[^\w\s.-]+", "", value)
    return re.sub(r"-+", "-", re.sub(r"[\s._]+", "-", value)).strip("-")


def _version_sort_key(slug: str) -> tuple[int, ...]:
    numbers = tuple(int(n) for n in re.findall(r"\d+", slug))
    return (*numbers, 0 if "initial" in slug.lower() else 1)
