"""Agent-facing operations, independent of any particular front end.

The CLI and the MCP server are both thin shells over this module, so a rule
extracted through either one comes back byte-identical — same envelope, same
provenance, same status. Everything here either returns an envelope (see
:mod:`easa_erules.contract`) or raises :class:`ToolError`.
"""

from __future__ import annotations

import base64
import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .contract import Status, ToolError, envelope
from .parser import ParseResult
from .sources.provenance import SourceProvenance, build_provenance


def _reject_if_not_convertible(source: str) -> None:
    """Fail early and clearly for catalog entries EASA publishes only as PDF."""
    from .sources.registry import get_source

    try:
        entry = get_source(source)
    except KeyError:
        return
    if entry.get("xml_available") is False:
        raise ToolError(
            Status.ERROR,
            f"{entry['id']} is published by EASA as PDF only — there is no XML "
            f"export to parse. See {entry.get('landing_page', 'the EASA document library')}.",
            source=source,
        )


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

    _reject_if_not_convertible(source)

    if authority_of(source) == "FAA":
        path = _resolve_faa_path(source, version=version, auto_fetch=auto_fetch)
        _verify_resolved_integrity(path)
        return path

    try:
        path = resolve_local_source(source, version=version, auto_fetch=auto_fetch)
        _verify_resolved_integrity(path)
        return path
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


def _verify_resolved_integrity(path: Path) -> None:
    """Verify a sidecar hash before ordinary cached reads."""
    import yaml

    from .sources.inventory import sha256_file

    meta_path = path.with_name("meta.yaml")
    if not meta_path.is_file():
        return
    try:
        metadata = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ToolError(
            Status.ERROR,
            f"Cached source metadata is unreadable: {exc}",
            source=str(path),
        ) from exc
    expected = (metadata.get("integrity") or {}).get("sha256")
    if not expected:
        raise ToolError(
            Status.ERROR,
            "Cached source metadata does not contain an integrity SHA-256.",
            source=str(path),
        )
    actual = sha256_file(path)
    if actual != expected:
        raise ToolError(
            Status.INTEGRITY_ERROR,
            "Cached source SHA-256 does not match meta.yaml.",
            source=str(path),
            expected_sha256=expected,
            actual_sha256=actual,
        )


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
        from .memory import parse_cached

        return parse_cached(path), path
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


def find_rules(node: Any, designation: str) -> list[Any]:
    """Every node matching a designation or ERules id (case/space insensitive).

    Usually one. An AMC or GM that covers several rules is printed once under
    each of them with the same ERulesId, so a lookup by id legitimately finds
    the same item several times.
    """
    needle = designation.replace(" ", "-").upper()
    found: list[Any] = []

    def matches(n: Any) -> bool:
        for attr in ("designation", "erules_id"):
            val = getattr(n, attr, None)
            if val and val.replace(" ", "-").upper() == needle:
                return True
        return False

    def walk(n: Any) -> None:
        if matches(n):
            found.append(n)
        for child in getattr(n, "children", []):
            walk(child)

    walk(node)
    return found


def find_rule(node: Any, designation: str) -> Any | None:
    """First node matching a designation or ERules id, or None."""
    matches = find_rules(node, designation)
    return matches[0] if matches else None


# --- Operations ------------------------------------------------------------


def clear_memory_cache() -> dict[str, Any]:
    """Clear the bounded in-process parse cache."""
    from .memory import clear_memory_cache as clear

    clear()
    return envelope(Status.OK, cache={"size": 0})


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

    versions = list_cached_versions(source["id"])["versions"]
    return envelope(
        Status.OK,
        regulation=dict(source),
        cached=str(cached) if cached else None,
        versions=versions,
    )


def list_cached_versions(
    doc_id: str,
    verify_integrity: bool = False,
) -> dict[str, Any]:
    """Return the local version inventory without any network access."""
    from .sources.inventory import list_cached_version_records
    from .sources.registry import resolve_source_id

    try:
        key = resolve_source_id(doc_id)
    except KeyError as exc:
        raise ToolError(Status.ERROR, f"Unknown document: {doc_id}", source=doc_id) from exc
    records = list_cached_version_records(key, verify_integrity=verify_integrity)
    return envelope(
        Status.OK,
        document_id=key,
        verify_integrity=verify_integrity,
        versions=[item.to_dict() for item in records],
    )


def list_remote_versions(doc_id: str) -> dict[str, Any]:
    """Discover remotely published EASA versions in newest-first order."""
    import httpx

    from .sources.registry import get_source
    from .sources.resolver import EasaSourceResolver, _publication_sort_key

    try:
        entry = get_source(doc_id)
    except KeyError as exc:
        raise ToolError(Status.ERROR, f"Unknown document: {doc_id}", source=doc_id) from exc

    convertible = entry.get("xml_available") is not False
    if not convertible:
        return envelope(
            Status.OK,
            document_id=entry["id"],
            convertible=False,
            landing_page=entry.get("landing_page"),
            versions=[],
        )
    if str(entry.get("authority", "")).upper() != "EASA":
        raise ToolError(
            Status.ERROR,
            "Remote version inventory is currently supported for EASA publications only.",
            source=doc_id,
        )

    checked_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with EasaSourceResolver() as resolver:
            resolved = resolver.resolve(entry["id"], preferred_format="xml")
    except httpx.HTTPError as exc:
        raise ToolError(
            Status.FETCH_FAILED,
            f"Remote version lookup failed: {exc}",
            source=doc_id,
        ) from exc
    except (LookupError, ValueError) as exc:
        raise ToolError(Status.SOURCE_DRIFT, str(exc), source=doc_id) from exc

    xml_versions = [pub for pub in resolved.publications if pub.format == "xml"]
    if not xml_versions:
        raise ToolError(
            Status.SOURCE_DRIFT,
            f"No XML publications found on {resolved.landing_page}",
            source=doc_id,
        )
    xml_versions.sort(key=_publication_sort_key, reverse=True)
    latest_slug = xml_versions[0].version_slug
    versions = [
        {
            "version_label": pub.version_label,
            "version_slug": pub.version_slug,
            "format": pub.format,
            "download_url": pub.download_url,
            "filename": pub.filename,
            "reported_size": pub.size,
            "is_latest": pub.version_slug == latest_slug,
            "checked_at": checked_at,
        }
        for pub in xml_versions
    ]
    return envelope(
        Status.OK,
        document_id=entry["id"],
        convertible=True,
        landing_page=resolved.landing_page,
        checked_at=checked_at,
        versions=versions,
    )


def check_regulation_version(
    doc_id: str,
    version: str,
    deep: bool = False,
) -> dict[str, Any]:
    """Verify one exact local amendment and compare it with EASA's inventory."""
    import httpx

    from .sources.downloader import EasaDownloader, _extract_xml_payload
    from .sources.inventory import resolve_cached_version
    from .sources.registry import resolve_source_id

    try:
        key = resolve_source_id(doc_id)
    except KeyError as exc:
        raise ToolError(Status.ERROR, f"Unknown document: {doc_id}", source=doc_id) from exc
    local = resolve_cached_version(key, version, verify_integrity=True)
    if local is None:
        raise ToolError(
            Status.NOT_CACHED,
            f"Exact cached version not found: {key}/{version}",
            source=doc_id,
        )
    if local.integrity_state == "mismatch":
        raise ToolError(
            Status.INTEGRITY_ERROR,
            "Cached source SHA-256 does not match meta.yaml.",
            source=str(local.source_path),
            expected_sha256=local.sha256,
            actual_sha256=local.actual_sha256,
        )
    if local.integrity_state != "ok":
        raise ToolError(
            Status.ERROR,
            f"Cached version cannot be verified: {local.integrity_state}",
            source=str(local.source_path),
        )

    checked_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    warnings: list[str] = []
    latest_slug: str | None = None
    remote_same: dict[str, Any] | None = None
    remote_sha: str | None = None
    state = "unknown"
    try:
        remote = list_remote_versions(key)
        versions = remote["versions"]
        latest_slug = next(
            (item["version_slug"] for item in versions if item["is_latest"]),
            None,
        )
        remote_same = next(
            (item for item in versions if item["version_slug"] == local.version_slug),
            None,
        )
        if remote_same is None:
            state = "remote_version_missing"
        else:
            meta_source = (local.metadata or {}).get("source") or {}
            shallow_changed = any(
                expected not in (None, "") and actual not in (None, "") and expected != actual
                for expected, actual in (
                    (meta_source.get("download_url"), remote_same.get("download_url")),
                    (meta_source.get("format"), remote_same.get("format")),
                    (meta_source.get("reported_size"), remote_same.get("reported_size")),
                )
            )
            if deep:
                with EasaDownloader() as downloader:
                    resolved = downloader.resolver.resolve(key, preferred_format="xml")
                    publication = next(
                        (
                            pub
                            for pub in resolved.publications
                            if pub.format == "xml" and pub.version_slug == local.version_slug
                        ),
                        None,
                    )
                    if publication is None:
                        state = "remote_version_missing"
                    else:
                        raw = downloader._download_bytes(publication.download_url)
                        xml_bytes, _ = _extract_xml_payload(raw, publication)
                        remote_sha = hashlib.sha256(xml_bytes).hexdigest()
                        shallow_changed = shallow_changed or remote_sha != local.actual_sha256
            if state != "remote_version_missing":
                if shallow_changed:
                    state = "remote_changed"
                elif latest_slug and latest_slug != local.version_slug:
                    state = "update_available"
                else:
                    state = "current"
    except (ToolError, httpx.HTTPError, LookupError, ValueError) as exc:
        warnings.append("remote_check_failed")
        warnings.append(str(exc))

    return envelope(
        Status.OK,
        warnings=warnings,
        document_id=key,
        local=local.to_dict(),
        freshness={
            "state": state,
            "local_version_slug": local.version_slug,
            "latest_remote_version_slug": latest_slug,
            "same_version_remote_sha256": remote_sha,
            "checked_at": checked_at,
            "deep_verified": bool(deep and remote_sha),
        },
    )


def delete_cached_version(doc_id: str, version_slug: str) -> dict[str, Any]:
    """Delete exactly one cached version and its version-specific index."""
    from .sources.cache import delete_version_directory
    from .sources.inventory import resolve_cached_version
    from .sources.registry import resolve_source_id

    try:
        key = resolve_source_id(doc_id)
    except KeyError as exc:
        raise ToolError(Status.ERROR, f"Unknown document: {doc_id}", source=doc_id) from exc
    cached = resolve_cached_version(key, version_slug)
    if cached is None or cached.version_slug != version_slug:
        raise ToolError(
            Status.NOT_CACHED,
            f"Exact cached version not found: {key}/{version_slug}",
            source=doc_id,
        )
    try:
        result = delete_version_directory(key, version_slug)
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise ToolError(Status.ERROR, str(exc), source=doc_id) from exc
    try:
        from .memory import clear_memory_cache

        clear_memory_cache(cached.source_path)
    except ImportError:  # pragma: no cover
        pass
    return envelope(Status.OK, **result)


def document_outline(source: str, version: str) -> dict[str, Any]:
    """Return the lightweight structural/navigation tree for one pinned version."""
    from .navigation import build_navigation

    result, source_path = parse_source(source, version=version, auto_fetch=False)
    prov = provenance_for(source, source_path, result.document)
    navigation = build_navigation(result.document)
    return envelope(
        Status.OK,
        source=prov.to_dict(),
        warnings=prov.warnings,
        document={
            "id": document_key(source, source_path),
            "title": result.document.title,
            "version_slug": prov.version_slug or version,
        },
        outline=navigation.outline,
    )


def get_rule_context(
    source: str,
    *,
    version: str,
    node_id: str | None = None,
    designation: str | None = None,
) -> dict[str, Any]:
    """Return one rule/AMC/GM plus navigation, relations and references."""
    from .navigation import build_navigation
    from .relations import build_relationship_map, identity_key
    from .render import render_html_fragment
    from .render.text import feature_flags, plain_text

    if (node_id is None) == (designation is None):
        raise ToolError(
            Status.ERROR,
            "Provide exactly one of node_id or designation.",
            source=source,
        )
    result, source_path = parse_source(source, version=version, auto_fetch=False)
    prov = provenance_for(source, source_path, result.document)
    navigation = build_navigation(result.document)
    if node_id is not None:
        matches = [node for node in navigation.navigable if node.id == node_id]
    else:
        matches = find_rules(result.document, designation or "")

    warnings = list(prov.warnings)
    if len(matches) > 1:
        warnings.append("repeated_in_source")
    if not matches:
        return envelope(
            Status.NO_MATCH,
            source=prov.to_dict(),
            warnings=warnings,
            query={"node_id": node_id, "designation": designation},
            item=None,
            breadcrumb=[],
            previous=None,
            next=None,
            related={"requirements": [], "amc": [], "gm": []},
            references={"outgoing": [], "incoming": []},
        )

    node = matches[0]
    key = document_key(source, source_path)
    relation_map = build_relationship_map(result.document, result.references)
    related = relation_map.related_for(node)
    positions = [i for i, item in enumerate(navigation.navigable) if item is node]
    position = positions[0] if positions else -1

    occurrence_ids = {
        item.id
        for item in navigation.navigable
        if identity_key(item) == identity_key(node)
    }
    outgoing = []
    incoming = []
    seen_out: set[tuple[Any, ...]] = set()
    seen_in: set[tuple[Any, ...]] = set()
    for occurrence_id in occurrence_ids:
        for ref in result.references.get_references_from(occurrence_id):
            payload = ref.to_dict()
            marker = tuple(sorted(payload.items()))
            if marker not in seen_out:
                seen_out.add(marker)
                outgoing.append(payload)
        for ref in result.references.get_references_to(occurrence_id):
            payload = ref.to_dict()
            marker = tuple(sorted(payload.items()))
            if marker not in seen_in:
                seen_in.add(marker)
                incoming.append(payload)

    return envelope(
        Status.OK,
        source=prov.to_dict(),
        warnings=warnings,
        query={"node_id": node_id, "designation": designation},
        occurrences=len(matches),
        item={
            "id": node.id,
            "erules_id": getattr(node, "erules_id", "") or "",
            "node_type": node.type.value,
            "material_category": _material_category(node, key),
            "designation": getattr(node, "designation", "") or "",
            "title": getattr(node, "title", "") or "",
            "plain_text": plain_text(node),
            "html": render_html_fragment(node),
        },
        breadcrumb=navigation.breadcrumb_by_id.get(node.id, []),
        previous=_node_summary(navigation.navigable[position - 1], key) if position > 0 else None,
        next=(
            _node_summary(navigation.navigable[position + 1], key)
            if 0 <= position < len(navigation.navigable) - 1
            else None
        ),
        related=related,
        references={"outgoing": outgoing, "incoming": incoming},
        features=feature_flags(node),
    )


def get_asset(source: str, asset_name: str, version: str) -> dict[str, Any]:
    """Return one parser-known asset; *asset_name* is never treated as a path."""
    if not asset_name or "/" in asset_name or "\\" in asset_name or asset_name in {".", ".."}:
        raise ToolError(Status.ERROR, "Invalid asset name.", source=source)
    result, source_path = parse_source(source, version=version, auto_fetch=False)
    asset = result.assets.get(asset_name)
    if asset is None:
        raise ToolError(
            Status.NO_MATCH,
            f"Unknown asset: {asset_name}",
            source=source,
        )
    prov = provenance_for(source, source_path, result.document)
    return envelope(
        Status.OK,
        source=prov.to_dict(),
        warnings=prov.warnings,
        asset={
            "name": asset.deterministic_name,
            "mime_type": asset.content_type,
            "sha256": asset.sha256,
            "size": asset.size,
            "content_base64": base64.b64encode(asset.data).decode("ascii"),
        },
    )


def prepare_regulation(
    source: str,
    version: str,
    *,
    auto_fetch: bool = False,
) -> dict[str, Any]:
    """Verify, parse, cache, index and precompute navigation/relations."""
    from .navigation import build_navigation
    from .relations import build_relationship_map
    from .render.text import feature_flags
    from .search import ensure_index
    from .sources.inventory import sha256_file

    source_path = resolve_source_path(source, version=version, auto_fetch=auto_fetch)
    warnings: list[str] = []
    meta_path = source_path.with_name("meta.yaml")
    if meta_path.is_file():
        import yaml

        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            expected = (meta.get("integrity") or {}).get("sha256")
        except (OSError, yaml.YAMLError) as exc:
            raise ToolError(Status.ERROR, f"Metadata unreadable: {exc}", source=str(meta_path)) from exc
        actual = sha256_file(source_path)
        if not expected or expected != actual:
            status = Status.INTEGRITY_ERROR if expected else Status.ERROR
            raise ToolError(
                status,
                "Cached source integrity metadata is missing or does not match.",
                source=str(source_path),
                expected_sha256=expected,
                actual_sha256=actual,
            )
    else:
        warnings.append("provenance_metadata_missing")

    parsed, _ = parse_source(source, version=version, auto_fetch=False)
    key = document_key(source, source_path)
    db_path = ensure_index(source_path, document_key=key)
    navigation = build_navigation(parsed.document)
    relations = build_relationship_map(parsed.document, parsed.references)
    flags = [feature_flags(node) for node in navigation.navigable]
    prov = provenance_for(source, source_path, parsed.document)
    warnings.extend(item for item in prov.warnings if item not in warnings)
    return envelope(
        Status.OK,
        source=prov.to_dict(),
        warnings=warnings,
        preparation={
            "version_slug": prov.version_slug or version,
            "source_path": str(source_path),
            "search_index": str(db_path),
            "outline_nodes": _count_outline_nodes(navigation.outline),
            "navigable_topics": len(navigation.navigable),
            "relationship_materials": len(relations.targets),
            "tables": sum(1 for item in flags if item["has_table"]),
            "figures": sum(1 for item in flags if item["has_figure"]),
            "parser_warnings": len(parsed.warnings),
        },
    )


def _material_category(node: Any, document_id: str) -> str:
    from .model import AcceptableMeansOfComplianceNode, GuidanceNode, RegulationRequirement

    if isinstance(node, AcceptableMeansOfComplianceNode):
        return "amc"
    if isinstance(node, GuidanceNode):
        return "gm"
    if isinstance(node, RegulationRequirement):
        return "implementing_rule" if document_id in {"part-21", "uas-rules"} else "certification_specification"
    return ""


def _node_summary(node: Any, document_id: str) -> dict[str, Any]:
    return {
        "id": node.id,
        "erules_id": getattr(node, "erules_id", "") or "",
        "node_type": node.type.value,
        "material_category": _material_category(node, document_id),
        "designation": getattr(node, "designation", "") or "",
        "title": getattr(node, "title", "") or "",
    }


def _count_outline_nodes(nodes: list[dict[str, Any]]) -> int:
    return sum(1 + _count_outline_nodes(node["children"]) for node in nodes)


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

    _reject_if_not_convertible(doc_id)

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
    except Exception as exc:
        from .sources.downloader import CachedIntegrityError

        if isinstance(exc, CachedIntegrityError):
            raise ToolError(Status.INTEGRITY_ERROR, str(exc), source=doc_id) from exc
        if isinstance(exc, LookupError):
            raise ToolError(Status.SOURCE_DRIFT, str(exc), source=doc_id) from exc
        raise ToolError(Status.FETCH_FAILED, f"Fetch failed: {exc}", source=doc_id) from exc

    _verify_resolved_integrity(result.source_path)
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
    matches = find_rules(result.document, rule)

    warnings = list(prov.warnings)
    if len(matches) > 1:
        # The publisher prints this item under each rule it covers. One body is
        # returned; the count says how many times it appears so an agent does
        # not mistake the pick for the whole picture.
        warnings.append("repeated_in_source")

    status = Status.OK if matches else Status.NO_MATCH
    return envelope(
        status,
        source=prov.to_dict(),
        warnings=warnings,
        query=rule,
        occurrences=len(matches),
        rule=render_json(matches[0]) if matches else None,
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
    text: str = "",
    *,
    version: str | None = None,
    limit: int = 20,
    offset: int = 0,
    material_categories: list[str] | None = None,
    structure_kinds: list[str] | None = None,
    within_node_id: str | None = None,
    has_table: bool | None = None,
    has_figure: bool | None = None,
    fields: list[str] | None = None,
    include_facets: bool = True,
    rebuild: bool = False,
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

    result = run_search(
        db_path,
        text,
        limit=limit,
        offset=offset,
        document_key=key,
        material_categories=material_categories,
        structure_kinds=structure_kinds,
        within_node_id=within_node_id,
        has_table=has_table,
        has_figure=has_figure,
        fields=fields,
        include_facets=include_facets,
    )
    prov = provenance_for(source, source_path, None)
    status = Status.OK if result.hits else Status.NO_MATCH
    return envelope(
        status,
        source=prov.to_dict(),
        warnings=prov.warnings,
        **result.to_dict(),
    )
