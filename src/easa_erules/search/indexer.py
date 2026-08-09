"""Build / refresh the SQLite search index from a Regulation AST."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .. import __version__
from ..input.package import OpcPackage
from ..model import (
    AcceptableMeansOfComplianceNode,
    GuidanceNode,
    InternalReferenceNode,
    ParagraphNode,
    RegulationDocument,
    RegulationRequirement,
    RegulationSection,
)
from ..model.assets import AssetCollection
from ..model.references import ReferenceIndex
from ..parser import EasaDocumentParser, ParseResult
from ..sources.cache import document_cache_dir
from .sqlite import connect, set_meta


def index_db_path(
    document_key: str,
    *,
    cache_root: Path | None = None,
) -> Path:
    """Path to the per-document SQLite index."""
    return document_cache_dir(document_key, cache_root) / "search.sqlite"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_index(
    source_path: Path,
    *,
    document_key: str | None = None,
    cache_root: Path | None = None,
    force: bool = False,
) -> Path:
    """Parse source if needed and build/refresh the search index.

    Returns path to the SQLite database.
    Invalidates when source SHA256 or parser version changes.
    """
    source_path = Path(source_path).resolve()
    key = (document_key or source_path.stem).lower()
    db_path = index_db_path(key, cache_root=cache_root)
    source_sha = sha256_file(source_path)

    if db_path.exists() and not force:
        conn = connect(db_path)
        try:
            row = conn.execute(
                "SELECT source_sha256, parser_version FROM documents WHERE document_key = ?",
                (key,),
            ).fetchone()
            if (
                row
                and row["source_sha256"] == source_sha
                and row["parser_version"] == __version__
            ):
                return db_path
        finally:
            conn.close()

    package = OpcPackage.from_file(source_path)
    result = EasaDocumentParser(package).parse()
    build_index(
        result,
        db_path=db_path,
        document_key=key,
        source_path=source_path,
        source_sha256=source_sha,
    )
    return db_path


def build_index(
    result: ParseResult,
    *,
    db_path: Path,
    document_key: str,
    source_path: Path | None = None,
    source_sha256: str = "",
) -> Path:
    """Write a full index for the parsed document (replaces existing rows)."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Rebuild cleanly for this document key
    if db_path.exists():
        db_path.unlink()

    conn = connect(db_path)
    try:
        _index_document(
            conn,
            result.document,
            document_key=document_key,
            source_path=str(source_path) if source_path else "",
            source_sha256=source_sha256 or "",
            assets=result.assets,
            references=result.references,
        )
        set_meta(conn, "schema_version", "1")
        set_meta(conn, "parser_version", __version__)
        conn.commit()
    finally:
        conn.close()
    return db_path


def _index_document(
    conn: sqlite3.Connection,
    doc: RegulationDocument,
    *,
    document_key: str,
    source_path: str,
    source_sha256: str,
    assets: AssetCollection | None,
    references: ReferenceIndex | None,
) -> None:
    indexed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute(
        """
        INSERT INTO documents(
            document_key, document_id, title, authority, version,
            source_path, source_sha256, parser_version, indexed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_key,
            doc.document_id or document_key,
            doc.title,
            doc.authority or "EASA",
            doc.version,
            source_path,
            source_sha256,
            __version__,
            indexed_at,
        ),
    )
    doc_rowid = cur.lastrowid

    def walk(node: Any, parent_topic_rowid: int | None = None) -> None:
        if isinstance(
            node,
            (
                RegulationRequirement,
                GuidanceNode,
                AcceptableMeansOfComplianceNode,
                RegulationSection,
            ),
        ):
            topic_type = node.type.value if node.type else "topic"
            text = _collect_text(node)
            meta = dict(getattr(node, "metadata", None) or {})
            designation = getattr(node, "designation", "") or ""
            erules_id = getattr(node, "erules_id", "") or ""
            title = getattr(node, "title", "") or ""
            cur = conn.execute(
                """
                INSERT INTO topics(
                    document_rowid, node_id, designation, erules_id,
                    title, topic_type, text_content, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_rowid,
                    node.id or designation or erules_id,
                    designation,
                    erules_id,
                    title,
                    topic_type,
                    text,
                    json.dumps(meta, ensure_ascii=False),
                ),
            )
            topic_rowid = cur.lastrowid
            for child in node.children:
                walk(child, topic_rowid)
            return

        if isinstance(node, ParagraphNode):
            text = node.get_text()
            conn.execute(
                """
                INSERT INTO paragraphs(document_rowid, topic_rowid, node_id, text_content)
                VALUES (?, ?, ?, ?)
                """,
                (doc_rowid, parent_topic_rowid, node.id or "", text),
            )

        for child in getattr(node, "children", []) or []:
            walk(child, parent_topic_rowid)

    for child in doc.children:
        walk(child, None)

    if references is not None:
        for ref in references.by_designation.values():
            conn.execute(
                """
                INSERT INTO references_idx(
                    document_rowid, source_node_id, target_designation,
                    target_id, raw_text, resolved
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_rowid,
                    ref.source_id,
                    ref.target_designation,
                    ref.target_id,
                    ref.raw_text,
                    1 if ref.resolved else 0,
                ),
            )
        # Also index inline unresolved refs found only in by_source
        for refs in references.by_source.values():
            for ref in refs:
                # may duplicate designation-keyed refs; OK for search
                pass

    if assets is not None:
        for name, asset in assets.assets.items():
            conn.execute(
                """
                INSERT INTO assets_idx(
                    document_rowid, deterministic_name, content_type, sha256, size
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    doc_rowid,
                    name,
                    asset.content_type,
                    asset.sha256,
                    asset.size,
                ),
            )


def _collect_text(node: Any) -> str:
    """Flatten plain text under a topic node (paragraphs + nested text)."""
    parts: list[str] = []

    def walk(n: Any) -> None:
        if isinstance(n, ParagraphNode):
            t = n.get_text().strip()
            if t:
                parts.append(t)
        elif isinstance(n, InternalReferenceNode):
            t = (n.text or n.target_designation or "").strip()
            if t:
                parts.append(t)
        for child in getattr(n, "children", []) or []:
            # Do not descend into nested requirements/sections as separate topics
            if isinstance(
                child,
                (
                    RegulationRequirement,
                    GuidanceNode,
                    AcceptableMeansOfComplianceNode,
                    RegulationSection,
                ),
            ):
                continue
            walk(child)

    walk(node)
    title = getattr(node, "title", "") or ""
    if title:
        parts.insert(0, title)
    return "\n".join(parts)
