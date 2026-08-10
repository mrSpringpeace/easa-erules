"""Agent-facing operations, independent of any particular front end.

The CLI and the MCP server are both thin shells over this module, so a rule
extracted through either one comes back byte-identical — same envelope, same
provenance, same status. Everything here either returns an envelope (see
:mod:`easa_erules.contract`) or raises :class:`ToolError`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .contract import Status, ToolError, envelope
from .parser import ParseResult
from .parsing import parse_any
from .sources.provenance import SourceProvenance, build_provenance


def authority_of(source: str) -> str:
    """Authority for a catalog id/alias; empty string for plain file paths."""
    from .sources.registry import get_source

    try:
        return str(get_source(source).get("authority", "")).upper()
    except KeyError:
        return ""


def resolve_source_path(
    source: str,
    *,
    version: str | None = None,
    auto_fetch: bool = False,
) -> Path:
    """Resolve a source argument (path, registry id or alias) to a local file."""
    import httpx

    from .sources import resolve_local_source
    from .sources.registry import resolve_source_id

    known = True
    try:
        resolve_source_id(source)
    except KeyError:
        known = Path(source).exists()

    if authority_of(source) == "FAA":
        return _resolve_faa_path(source, version=version, auto_fetch=auto_fetch)

    try:
        return resolve_local_source(source, version=version, auto_fetch=auto_fetch)
    except FileNotFoundError as exc:
        if not known:
            raise ToolError(
                Status.ERROR,
                f"Unknown source: {source}. Run 'easa-erules list' to see the catalog.",
                source=source,
            ) from exc
        raise ToolError(Status.NOT_CACHED, str(exc), source=source) from exc
    except LookupError as exc:
        raise ToolError(Status.SOURCE_DRIFT, str(exc), source=source) from exc
    except httpx.HTTPError as exc:
        raise ToolError(Status.FETCH_FAILED, f"Download failed: {exc}", source=source) from exc


def _resolve_faa_path(
    source: str,
    *,
    version: str | None = None,
    auto_fetch: bool = False,
) -> Path:
    """Cache lookup / eCFR download for an FAA catalog entry."""
    import httpx

    from .adapters.faa import FaaEcfrAdapter
    from .sources.cache import document_cache_dir, version_cache_dir
    from .sources.registry import resolve_source_id

    key = resolve_source_id(source)
    cached = (
        version_cache_dir(key, version) / "source.xml"
        if version
        else document_cache_dir(key) / "source.xml"
    )
    if cached.is_file():
        return cached

    if not auto_fetch:
        raise ToolError(
            Status.NOT_CACHED,
            f"Source '{key}' is registered but not available in the local cache. "
            f"Run: easa-erules fetch {key}" + (f" --version {version}" if version else ""),
            source=source,
        )

    try:
        return FaaEcfrAdapter().fetch(key, version=version)
    except httpx.HTTPError as exc:
        raise ToolError(Status.FETCH_FAILED, f"eCFR download failed: {exc}", source=source) from exc
    except ValueError as exc:
        raise ToolError(Status.ERROR, str(exc), source=source) from exc


def parse_source(
    source: str,
    *,
    version: str | None = None,
    auto_fetch: bool = False,
) -> tuple[ParseResult, Path]:
    """Resolve, load and parse in one step, picking the parser from the source."""
    path = resolve_source_path(source, version=version, auto_fetch=auto_fetch)
    try:
        return parse_any(path), path
    except Exception as exc:
        raise ToolError(Status.PARSE_ERROR, f"Parse error: {exc}", source=str(path)) from exc


def document_key(source: str, source_path: Path) -> str:
    """Registry id when the argument names a catalog entry, else the file stem."""
    from .sources.registry import resolve_source_id

    try:
        return resolve_source_id(source)
    except KeyError:
        return source_path.stem


def provenance_for(source: str, source_path: Path, document: Any) -> SourceProvenance:
    """Provenance tuple for a resolved source."""
    return build_provenance(
        source_path,
        document_key=document_key(source, source_path),
        document=document,
    )


def find_rule(node: Any, designation: str) -> Any | None:
    """Find a rule node by designation or ERules id (case/space insensitive)."""
    needle = designation.replace(" ", "-").upper()

    def matches(n: Any) -> bool:
        for attr in ("designation", "erules_id"):
            val = getattr(n, attr, None)
            if val and val.replace(" ", "-").upper() == needle:
                return True
        return False

    if matches(node):
        return node
    for child in getattr(node, "children", []):
        found = find_rule(child, designation)
        if found:
            return found
    return None


# --- Operations ------------------------------------------------------------


def list_regulations() -> dict[str, Any]:
    """Built-in catalog of regulation sources (EASA and FAA)."""
    from .sources import list_sources

    return envelope(Status.OK, regulations=list_sources())


def regulation_info(doc_id: str) -> dict[str, Any]:
    """Catalog entry plus local cache state for one publication."""
    from .sources import get_source
    from .sources.downloader import EasaDownloader

    try:
        source = get_source(doc_id)
    except KeyError as exc:
        raise ToolError(
            Status.ERROR,
            f"Unknown document: {doc_id}. Run 'easa-erules list' to see the catalog.",
            source=doc_id,
        ) from exc

    downloader = EasaDownloader()
    try:
        cached = downloader.local_source_path(source["id"])
    finally:
        downloader.close()

    return envelope(
        Status.OK,
        regulation=dict(source),
        cached=str(cached) if cached else None,
    )


def fetch_regulation(
    doc_id: str,
    *,
    version: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Download a publication into the local cache. Requires network access."""
    from .sources import EasaDownloader, get_source

    try:
        entry = get_source(doc_id)
    except KeyError as exc:
        raise ToolError(
            Status.ERROR,
            f"Unknown document: {doc_id}. Run 'easa-erules list' to see the catalog.",
            source=doc_id,
        ) from exc

    if str(entry.get("authority", "")).upper() == "FAA":
        path = _resolve_faa_path(doc_id, version=version, auto_fetch=True)
        prov = provenance_for(doc_id, path, None)
        return envelope(
            Status.OK,
            source=prov.to_dict(),
            warnings=prov.warnings,
            fetch={"document_id": entry["id"], "source_path": str(path), "from_cache": False},
        )

    try:
        with EasaDownloader() as downloader:
            result = downloader.fetch(doc_id, version=version, force=force)
    except LookupError as exc:
        raise ToolError(Status.SOURCE_DRIFT, str(exc), source=doc_id) from exc
    except Exception as exc:
        raise ToolError(Status.FETCH_FAILED, f"Fetch failed: {exc}", source=doc_id) from exc

    prov = provenance_for(doc_id, result.source_path, None)
    return envelope(
        Status.OK,
        source=prov.to_dict(),
        warnings=prov.warnings,
        fetch=result.to_dict(),
    )


def extract_rule(
    source: str,
    rule: str,
    *,
    version: str | None = None,
    auto_fetch: bool = False,
) -> dict[str, Any]:
    """Single rule, AMC or GM by designation."""
    from .render import render_json

    result, source_path = parse_source(source, version=version, auto_fetch=auto_fetch)
    prov = provenance_for(source, source_path, result.document)
    target = find_rule(result.document, rule)

    status = Status.OK if target is not None else Status.NO_MATCH
    return envelope(
        status,
        source=prov.to_dict(),
        warnings=prov.warnings,
        query=rule,
        rule=render_json(target) if target is not None else None,
    )


def rule_references(
    source: str,
    rule: str,
    *,
    version: str | None = None,
    auto_fetch: bool = False,
) -> dict[str, Any]:
    """Outgoing and incoming cross-references for a rule."""
    from .model.graph import lookup_refs

    result, source_path = parse_source(source, version=version, auto_fetch=auto_fetch)
    prov = provenance_for(source, source_path, result.document)
    node = lookup_refs(result.document, rule)

    status = Status.OK if node is not None else Status.NO_MATCH
    return envelope(
        status,
        source=prov.to_dict(),
        warnings=prov.warnings,
        query=rule,
        refs=node.to_dict() if node is not None else None,
    )


def query_regulation(
    source: str,
    text: str,
    *,
    limit: int = 20,
    rebuild: bool = False,
    version: str | None = None,
    auto_fetch: bool = False,
) -> dict[str, Any]:
    """Full-text search over one publication using the local FTS5 index."""
    from .search import ensure_index
    from .search import search as run_search

    source_path = resolve_source_path(source, version=version, auto_fetch=auto_fetch)
    key = document_key(source, source_path)

    try:
        db_path = ensure_index(source_path, document_key=key, force=rebuild)
    except ToolError:
        raise
    except sqlite3.Error as exc:
        raise ToolError(
            Status.INDEX_MISSING,
            f"Search index is unusable: {exc}. Retry with --rebuild.",
            source=str(source_path),
        ) from exc
    except Exception as exc:
        # The index is built by parsing the source, so a failure here is a
        # parse failure — reporting it as a missing index would send an agent
        # off to rebuild something that was never the problem.
        raise ToolError(
            Status.PARSE_ERROR,
            f"Source could not be indexed: {exc}",
            source=str(source_path),
        ) from exc

    result = run_search(db_path, text, limit=limit, document_key=key)
    prov = provenance_for(source, source_path, None)
    status = Status.OK if result.hits else Status.NO_MATCH
    return envelope(
        status,
        source=prov.to_dict(),
        warnings=prov.warnings,
        **result.to_dict(),
    )
