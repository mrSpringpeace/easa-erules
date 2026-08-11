"""Build and invalidate version-specific SQLite search indexes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .. import __version__
from ..memory import parse_cached
from ..model import (
    AcceptableMeansOfComplianceNode,
    GuidanceNode,
    RegulationDocument,
    RegulationRequirement,
)
from ..model.assets import AssetCollection
from ..model.references import ReferenceIndex
from ..navigation import build_navigation
from ..parser import ParseResult
from ..render.text import feature_flags, plain_text
from ..sources.cache import document_cache_dir
from .sqlite import INDEX_SCHEMA_VERSION, connect, get_meta, set_meta


def index_db_path(
    document_key: str,
    *,
    cache_root: Path | None = None,
    source_path: Path | None = None,
) -> Path:
    """Return per-version DB beside cached source, else legacy ad-hoc path."""
    if source_path is not None:
        source = Path(source_path).resolve()
        if source.name == "source.xml" and source.parent.parent.name == "versions":
            return source.parent / "search.sqlite"
    return document_cache_dir(document_key, cache_root) / "search.sqlite"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_index(
    source_path: Path,
    *,
    document_key: str | None = None,
    cache_root: Path | None = None,
    force: bool = False,
) -> Path:
    """Build/refresh an index invalidated by schema, parser or source SHA."""
    source_path = Path(source_path).resolve()
    key = (document_key or source_path.stem).lower()
    db_path = index_db_path(key, cache_root=cache_root, source_path=source_path)
    source_sha = sha256_file(source_path)

    if db_path.exists() and not force:
        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT source_sha256, parser_version FROM documents WHERE document_key = ?",
                (key,),
            ).fetchone()
            if (
                get_meta(conn, "schema_version") == INDEX_SCHEMA_VERSION
                and row
                and row["source_sha256"] == source_sha
                and row["parser_version"] == __version__
            ):
                return db_path
        finally:
            conn.close()

    result = parse_cached(source_path)
    return build_index(
        result,
        db_path=db_path,
        document_key=key,
        source_path=source_path,
        source_sha256=source_sha,
    )


def build_index(
    result: ParseResult,
    *,
    db_path: Path,
    document_key: str,
    source_path: Path | None = None,
    source_sha256: str = "",
) -> Path:
    """Atomically replace the full index contents for one document version."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = connect(db_path)
    try:
        _index_document(
            conn,
            result.document,
            document_key=document_key,
            source_path=str(source_path) if source_path else "",
            source_sha256=source_sha256,
            assets=result.assets,
            references=result.references,
        )
        set_meta(conn, "schema_version", INDEX_SCHEMA_VERSION)
        set_meta(conn, "parser_version", __version__)
        set_meta(conn, "source_sha256", source_sha256)
        conn.commit()
    finally:
        conn.close()
    return db_path


def _index_document(
    conn: sqlite3.Connection,
    document: RegulationDocument,
    *,
    document_key: str,
    source_path: str,
    source_sha256: str,
    assets: AssetCollection | None,
    references: ReferenceIndex | None,
) -> None:
    indexed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    cursor = conn.execute(
        """
        INSERT INTO documents(
            document_key, document_id, title, authority, version,
            source_path, source_sha256, parser_version, indexed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_key,
            document.document_id or document_key,
            document.title,
            document.authority or "EASA",
            document.version,
            source_path,
            source_sha256,
            __version__,
            indexed_at,
        ),
    )
    document_rowid = int(cursor.lastrowid or 0)
    navigation = build_navigation(document)

    for ordinal, node in enumerate(navigation.navigable, start=1):
        flags = feature_flags(node)
        crumbs = navigation.breadcrumb_by_id.get(node.id, [])
        path_text = " > ".join(
            item["designation"] or item["title"] for item in crumbs if item["designation"] or item["title"]
        )
        material = _material_category(node, document_key)
        structure = navigation.structure_kind_by_id.get(node.id, "section")
        cursor = conn.execute(
            """
            INSERT INTO topics(
                document_rowid, node_id, designation, erules_id, title,
                topic_type, ordinal, material_category, structure_kind,
                has_table, has_figure, is_definition, path_text, path_json,
                plain_text, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_rowid,
                node.id,
                getattr(node, "designation", "") or "",
                getattr(node, "erules_id", "") or "",
                getattr(node, "title", "") or "",
                node.type.value,
                ordinal,
                material,
                structure,
                int(flags["has_table"]),
                int(flags["has_figure"]),
                int(structure == "definitions"),
                path_text,
                json.dumps(crumbs, ensure_ascii=False),
                plain_text(node),
                json.dumps(getattr(node, "metadata", {}) or {}, ensure_ascii=False),
            ),
        )
        topic_rowid = int(cursor.lastrowid or 0)
        ancestors = navigation.ancestors_by_id.get(node.id, [])
        for depth, ancestor in enumerate(reversed(ancestors), start=1):
            conn.execute(
                "INSERT OR IGNORE INTO topic_ancestors(topic_rowid, ancestor_node_id, depth) "
                "VALUES (?, ?, ?)",
                (topic_rowid, ancestor, depth),
            )

    if references is not None:
        seen: set[tuple[str, str, str, str]] = set()
        for refs in references.by_source.values():
            for ref in refs:
                marker = (ref.source_id, ref.target_designation, ref.target_id, ref.raw_text)
                if marker in seen:
                    continue
                seen.add(marker)
                conn.execute(
                    """
                    INSERT INTO references_idx(
                        document_rowid, source_node_id, target_designation,
                        target_id, raw_text, resolved
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_rowid,
                        ref.source_id,
                        ref.target_designation,
                        ref.target_id,
                        ref.raw_text,
                        int(ref.resolved),
                    ),
                )

    if assets is not None:
        for name, asset in assets.assets.items():
            conn.execute(
                """
                INSERT INTO assets_idx(
                    document_rowid, deterministic_name, content_type, sha256, size
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (document_rowid, name, asset.content_type, asset.sha256, asset.size),
            )


def _material_category(node: object, document_key: str) -> str:
    if isinstance(node, AcceptableMeansOfComplianceNode):
        return "amc"
    if isinstance(node, GuidanceNode):
        return "gm"
    if isinstance(node, RegulationRequirement):
        return "implementing_rule" if document_key in {"part-21", "uas-rules"} else "certification_specification"
    return ""


def _collect_text(node: object) -> str:
    """Backward-compatible alias for the corrected table-aware collector."""
    return plain_text(node)
