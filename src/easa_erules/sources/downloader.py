"""Download EASA publications into the local cache with integrity metadata."""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

from .. import __version__
from .cache import (
    default_cache_root,
    document_cache_dir,
    latest_pointer_path,
    version_cache_dir,
)
from .resolver import DEFAULT_USER_AGENT, EasaSourceResolver, Publication, ResolveResult


@dataclass(slots=True)
class FetchResult:
    """Result of fetching a document into the local cache."""

    document_id: str
    version_label: str
    version_slug: str
    source_path: Path
    meta_path: Path
    sha256: str
    size: int
    download_url: str
    landing_page: str
    retrieved_at: str
    from_cache: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "version_label": self.version_label,
            "version_slug": self.version_slug,
            "source_path": str(self.source_path),
            "meta_path": str(self.meta_path),
            "sha256": self.sha256,
            "size": self.size,
            "download_url": self.download_url,
            "landing_page": self.landing_page,
            "retrieved_at": self.retrieved_at,
            "from_cache": self.from_cache,
        }


class EasaDownloader:
    """Download and cache EASA Easy Access Rules XML publications."""

    def __init__(
        self,
        cache_root: Path | None = None,
        client: httpx.Client | None = None,
        resolver: EasaSourceResolver | None = None,
        timeout: float = 120.0,
    ):
        self.cache_root = Path(cache_root) if cache_root else default_cache_root()
        self._owns_client = client is None and resolver is None
        self.client = client or httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        )
        self.resolver = resolver or EasaSourceResolver(client=self.client)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "EasaDownloader":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch(
        self,
        doc_id: str,
        *,
        version: str | None = None,
        force: bool = False,
        preferred_format: str = "xml",
    ) -> FetchResult:
        """Resolve, download (if needed), extract XML, write integrity metadata."""
        resolved = self.resolver.resolve(
            doc_id,
            version=version,
            preferred_format=preferred_format,
        )
        if not resolved.selected:
            raise LookupError(
                f"No {preferred_format!r} publication found for '{resolved.document_id}' "
                f"on {resolved.landing_page}"
            )

        pub = resolved.selected
        vdir = version_cache_dir(resolved.document_id, pub.version_slug, self.cache_root)
        source_path = vdir / "source.xml"
        meta_path = vdir / "meta.yaml"

        if source_path.exists() and meta_path.exists() and not force:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            return FetchResult(
                document_id=resolved.document_id,
                version_label=pub.version_label,
                version_slug=pub.version_slug,
                source_path=source_path,
                meta_path=meta_path,
                sha256=meta.get("integrity", {}).get("sha256")
                or _sha256_file(source_path),
                size=int(meta.get("integrity", {}).get("size") or source_path.stat().st_size),
                download_url=pub.download_url,
                landing_page=resolved.landing_page,
                retrieved_at=meta.get("retrieved_at") or "",
                from_cache=True,
            )

        vdir.mkdir(parents=True, exist_ok=True)
        raw_bytes = self._download_bytes(pub.download_url)
        xml_bytes, original_name = _extract_xml_payload(raw_bytes, pub)

        # Optionally keep original download for audit
        if original_name and original_name.lower().endswith(".zip"):
            (vdir / "original.zip").write_bytes(raw_bytes)
        elif not original_name or not original_name.lower().endswith(".xml"):
            (vdir / "original.bin").write_bytes(raw_bytes)

        source_path.write_bytes(xml_bytes)
        sha = hashlib.sha256(xml_bytes).hexdigest()
        retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        meta = {
            "document": resolved.document_id,
            "title": resolved.title,
            "authority": "EASA",
            "version": {
                "label": pub.version_label,
                "slug": pub.version_slug,
            },
            "source": {
                "landing_page": resolved.landing_page,
                "download_url": pub.download_url,
                "filename": pub.filename or original_name,
                "format": pub.format,
            },
            "retrieved_at": retrieved_at,
            "integrity": {
                "sha256": sha,
                "size": len(xml_bytes),
            },
            "parser": {
                "version": __version__,
            },
            "cache": {
                "root": str(self.cache_root),
                "path": str(source_path),
            },
        }
        meta_path.write_text(
            yaml.dump(meta, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        # Update latest pointer when fetching unpinned latest
        if version is None:
            latest_pointer_path(resolved.document_id, self.cache_root).write_text(
                pub.version_slug + "\n",
                encoding="utf-8",
            )
            # Convenience copy/symlink at document root
            latest_xml = document_cache_dir(resolved.document_id, self.cache_root) / "source.xml"
            latest_meta = document_cache_dir(resolved.document_id, self.cache_root) / "meta.yaml"
            latest_xml.write_bytes(xml_bytes)
            latest_meta.write_text(meta_path.read_text(encoding="utf-8"), encoding="utf-8")

        return FetchResult(
            document_id=resolved.document_id,
            version_label=pub.version_label,
            version_slug=pub.version_slug,
            source_path=source_path,
            meta_path=meta_path,
            sha256=sha,
            size=len(xml_bytes),
            download_url=pub.download_url,
            landing_page=resolved.landing_page,
            retrieved_at=retrieved_at,
            from_cache=False,
        )

    def local_source_path(
        self,
        doc_id: str,
        *,
        version: str | None = None,
    ) -> Path | None:
        """Return a cached source.xml path if present, else None."""
        from .registry import resolve_source_id

        key = resolve_source_id(doc_id)
        if version:
            from .resolver import _slugify_version

            slug = _slugify_version(version)
            path = version_cache_dir(key, slug, self.cache_root) / "source.xml"
            if path.exists():
                return path
            # try partial match under versions/
            versions_root = document_cache_dir(key, self.cache_root) / "versions"
            if versions_root.is_dir():
                for child in versions_root.iterdir():
                    if slug in child.name and (child / "source.xml").exists():
                        return child / "source.xml"
            return None

        latest = document_cache_dir(key, self.cache_root) / "source.xml"
        if latest.exists():
            return latest

        pointer = latest_pointer_path(key, self.cache_root)
        if pointer.exists():
            slug = pointer.read_text(encoding="utf-8").strip()
            path = version_cache_dir(key, slug, self.cache_root) / "source.xml"
            if path.exists():
                return path
        return None

    def _download_bytes(self, url: str) -> bytes:
        response = self.client.get(url)
        response.raise_for_status()
        return response.content


def _extract_xml_payload(data: bytes, pub: Publication) -> tuple[bytes, str | None]:
    """Return (xml_bytes, original_filename_hint)."""
    name = pub.filename or ""

    # ZIP container (typical EASA XML package)
    if data[:2] == b"PK" or name.lower().endswith(".zip") or (
        pub.content_type and "zip" in pub.content_type.lower()
    ):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml_names = [
                n for n in zf.namelist()
                if n.lower().endswith(".xml") and not n.endswith("/")
            ]
            if not xml_names:
                raise ValueError("Downloaded ZIP does not contain any .xml files")
            # Prefer largest XML (main Flat OPC document)
            xml_names.sort(key=lambda n: zf.getinfo(n).file_size, reverse=True)
            chosen = xml_names[0]
            return zf.read(chosen), name or "download.zip"

    # Raw XML / Flat OPC
    head = data.lstrip()[:100].lower()
    if head.startswith(b"<?xml") or head.startswith(b"<pkg:package") or name.lower().endswith(".xml"):
        return data, name or "download.xml"

    raise ValueError(
        f"Downloaded content is not XML or ZIP (content-type={pub.content_type!r}, "
        f"filename={name!r})"
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_local_source(
    source: str,
    *,
    cache_root: Path | None = None,
    auto_fetch: bool = False,
    version: str | None = None,
) -> Path:
    """Resolve a CLI source argument to a local filesystem path.

    Accepts:
    - existing file path
    - registry id / alias (uses cache; optionally fetches)
    """
    path = Path(source)
    if path.exists():
        return path.resolve()

    downloader = EasaDownloader(cache_root=cache_root)
    try:
        cached = downloader.local_source_path(source, version=version)
        if cached:
            return cached
        if auto_fetch:
            result = downloader.fetch(source, version=version)
            return result.source_path
    except KeyError:
        raise FileNotFoundError(f"File not found and unknown source id: {source}") from None
    finally:
        downloader.close()

    raise FileNotFoundError(
        f"Source '{source}' is registered but not available in the local cache. "
        f"Run: easa-erules fetch {source}"
        + (f" --version {version}" if version else "")
    )
