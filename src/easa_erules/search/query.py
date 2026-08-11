"""Filtered, paginated querying of the local FTS5 index."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence, cast

from ..contract import Status, ToolError
from .sqlite import connect

MATERIAL_CATEGORIES = {
    "implementing_rule",
    "certification_specification",
    "amc",
    "gm",
}
STRUCTURE_KINDS = {
    "part",
    "book",
    "subpart",
    "chapter",
    "section",
    "appendix",
    "definitions",
}
SEARCH_FIELDS = {"designation", "title", "body"}


@dataclass(slots=True)
class SearchHit:
    designation: str
    erules_id: str
    title: str
    topic_type: str
    node_id: str
    snippet: str
    rank: float
    text_preview: str = ""
    match_source: str = "topic"
    material_category: str = ""
    structure_kind: str = ""
    breadcrumb: list[dict[str, Any]] = field(default_factory=list)
    has_table: bool = False
    has_figure: bool = False
    ordinal: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "designation": self.designation,
            "erules_id": self.erules_id,
            "title": self.title,
            "type": self.topic_type,
            "id": self.node_id,
            "snippet": self.snippet,
            "rank": self.rank,
            "text_preview": self.text_preview,
            "match_source": self.match_source,
            "material_category": self.material_category,
            "structure_kind": self.structure_kind,
            "breadcrumb": self.breadcrumb,
            "path": self.breadcrumb,
            "features": {
                "has_table": self.has_table,
                "has_figure": self.has_figure,
            },
            "ordinal": self.ordinal,
        }


@dataclass(slots=True)
class SearchResult:
    document_key: str
    document_id: str
    title: str
    query: str
    hits: list[SearchHit] = field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0
    applied_filters: dict[str, Any] = field(default_factory=dict)
    facets: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": {
                "key": self.document_key,
                "id": self.document_id,
                "title": self.title,
            },
            "query": self.query,
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "applied_filters": self.applied_filters,
            "facets": self.facets,
            "hits": [hit.to_dict() for hit in self.hits],
        }


def prepare_fts_query(user_query: str) -> str:
    """Convert input into a safe AND expression while retaining quoted phrases."""
    query = user_query.strip()
    if not query:
        return ""
    phrases: list[str] = []

    def keep_phrase(match: re.Match[str]) -> str:
        phrases.append(" ".join(match.group(1).split()))
        return f" __PHRASE{len(phrases) - 1}__ "

    query = re.sub(r'"([^"]+)"', keep_phrase, query)
    query = re.sub(r"[^\w\s\-./]", " ", query, flags=re.UNICODE)
    tokens = [token for token in query.split() if token and not token.startswith("__PHRASE")]
    parts = [f'"{phrase.replace(chr(34), chr(34) * 2)}"' for phrase in phrases]
    parts.extend(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
    return " AND ".join(parts)


def search(
    db_path: Path | str,
    query: str,
    *,
    limit: int = 20,
    offset: int = 0,
    document_key: str | None = None,
    material_categories: Sequence[str] | None = None,
    structure_kinds: Sequence[str] | None = None,
    within_node_id: str | None = None,
    has_table: bool | None = None,
    has_figure: bool | None = None,
    fields: Sequence[str] | None = None,
    include_facets: bool = True,
) -> SearchResult:
    """Search or browse one indexed version with AND-between-filter-groups semantics."""
    if limit < 1:
        raise ToolError(Status.ERROR, "limit must be at least 1")
    if offset < 0:
        raise ToolError(Status.ERROR, "offset must not be negative")
    materials = _validated_values("material_categories", material_categories, MATERIAL_CATEGORIES)
    structures = _validated_values("structure_kinds", structure_kinds, STRUCTURE_KINDS)
    selected_fields = _validated_values("fields", fields, SEARCH_FIELDS)
    fts_query = prepare_fts_query(query)
    if fts_query and selected_fields:
        columns = ["plain_text" if item == "body" else item for item in selected_fields]
        fts_query = "{" + " ".join(columns) + "} : (" + fts_query + ")"

    applied_filters: dict[str, Any] = {}
    if materials:
        applied_filters["material_categories"] = materials
    if structures:
        applied_filters["structure_kinds"] = structures
    if within_node_id:
        applied_filters["within_node_id"] = within_node_id
    if has_table is not None:
        applied_filters["has_table"] = has_table
    if has_figure is not None:
        applied_filters["has_figure"] = has_figure
    if selected_fields:
        applied_filters["fields"] = selected_fields

    conn = connect(db_path)
    try:
        document = _select_document(conn, document_key)
        if not document:
            return SearchResult(document_key or "", "", "", query, limit=limit, offset=offset)
        if not fts_query and not applied_filters:
            return SearchResult(
                document["document_key"],
                document["document_id"],
                document["title"] or "",
                query,
                limit=limit,
                offset=offset,
            )

        join, conditions, params = _query_parts(
            int(document["id"]),
            fts_query=fts_query,
            materials=materials,
            structures=structures,
            within_node_id=within_node_id,
            has_table=has_table,
            has_figure=has_figure,
        )
        where = " AND ".join(conditions)
        total = int(
            conn.execute(
                f"SELECT COUNT(*) FROM topics t {join} WHERE {where}",  # noqa: S608
                params,
            ).fetchone()[0]
        )
        needle = _normalize_designation(query)
        if fts_query:
            select_snippet = "snippet(topics_fts, 2, '«', '»', '…', 24)"
            select_score = "bm25(topics_fts)"
            order = (
                "CASE WHEN UPPER(REPLACE(t.designation, ' ', '-')) = ? THEN 0 ELSE 1 END, "
                "score, t.ordinal"
            )
            row_params = [*params, needle, limit, offset]
        else:
            select_snippet = "substr(t.plain_text, 1, 280)"
            select_score = "0.0"
            order = "t.ordinal"
            row_params = [*params, limit, offset]
        rows = conn.execute(
            f"""
            SELECT t.*, {select_snippet} AS snip, {select_score} AS score
            FROM topics t {join}
            WHERE {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?
            """,  # noqa: S608
            row_params,
        ).fetchall()
        hits = [_hit_from_row(row) for row in rows]
        facets = _facets(conn, join, where, params) if include_facets else {}
        return SearchResult(
            document_key=document["document_key"],
            document_id=document["document_id"],
            title=document["title"] or "",
            query=query,
            hits=hits,
            total=total,
            limit=limit,
            offset=offset,
            applied_filters=applied_filters,
            facets=facets,
        )
    finally:
        conn.close()


def _query_parts(
    document_rowid: int,
    *,
    fts_query: str,
    materials: list[str],
    structures: list[str],
    within_node_id: str | None,
    has_table: bool | None,
    has_figure: bool | None,
) -> tuple[str, list[str], list[Any]]:
    join = "JOIN topics_fts ON topics_fts.rowid = t.id" if fts_query else ""
    conditions = ["t.document_rowid = ?"]
    params: list[Any] = [document_rowid]
    if fts_query:
        conditions.append("topics_fts MATCH ?")
        params.append(fts_query)
    for column, values in (("material_category", materials), ("structure_kind", structures)):
        if values:
            conditions.append(f"t.{column} IN ({','.join('?' for _ in values)})")
            params.extend(values)
    if within_node_id:
        conditions.append(
            "EXISTS (SELECT 1 FROM topic_ancestors a "
            "WHERE a.topic_rowid = t.id AND a.ancestor_node_id = ?)"
        )
        params.append(within_node_id)
    if has_table is not None:
        conditions.append("t.has_table = ?")
        params.append(int(has_table))
    if has_figure is not None:
        conditions.append("t.has_figure = ?")
        params.append(int(has_figure))
    return join, conditions, params


def _facets(
    conn: sqlite3.Connection,
    join: str,
    where: str,
    params: list[Any],
) -> dict[str, Any]:
    def counts(column: str) -> dict[str, int]:
        rows = conn.execute(
            f"SELECT t.{column} AS value, COUNT(*) AS count "
            f"FROM topics t {join} WHERE {where} GROUP BY t.{column}",  # noqa: S608
            params,
        ).fetchall()
        return {str(row["value"]): int(row["count"]) for row in rows if row["value"]}

    features = conn.execute(
        f"SELECT SUM(t.has_table) AS tables, SUM(t.has_figure) AS figures "
        f"FROM topics t {join} WHERE {where}",  # noqa: S608
        params,
    ).fetchone()
    return {
        "material_categories": counts("material_category"),
        "structure_kinds": counts("structure_kind"),
        "has_table": int(features["tables"] or 0),
        "has_figure": int(features["figures"] or 0),
    }


def _select_document(conn: sqlite3.Connection, document_key: str | None) -> sqlite3.Row | None:
    if document_key:
        return cast(sqlite3.Row | None, conn.execute(
            "SELECT * FROM documents WHERE document_key = ?", (document_key.lower(),)
        ).fetchone())
    return cast(
        sqlite3.Row | None,
        conn.execute("SELECT * FROM documents ORDER BY id DESC LIMIT 1").fetchone(),
    )


def _hit_from_row(row: sqlite3.Row) -> SearchHit:
    try:
        breadcrumb = json.loads(row["path_json"] or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        breadcrumb = []
    text = row["plain_text"] or ""
    return SearchHit(
        designation=row["designation"] or "",
        erules_id=row["erules_id"] or "",
        title=row["title"] or "",
        topic_type=row["topic_type"] or "",
        node_id=row["node_id"] or "",
        snippet=row["snip"] or text[:280],
        rank=float(row["score"] or 0.0),
        text_preview=text[:280],
        material_category=row["material_category"] or "",
        structure_kind=row["structure_kind"] or "",
        breadcrumb=breadcrumb if isinstance(breadcrumb, list) else [],
        has_table=bool(row["has_table"]),
        has_figure=bool(row["has_figure"]),
        ordinal=int(row["ordinal"]),
    )


def _validated_values(
    name: str,
    values: Sequence[str] | None,
    allowed: set[str],
) -> list[str]:
    result = list(dict.fromkeys(values or []))
    invalid = [value for value in result if value not in allowed]
    if invalid:
        raise ToolError(
            Status.ERROR,
            f"Invalid {name}: {', '.join(invalid)}. Allowed: {', '.join(sorted(allowed))}",
        )
    return result


def _normalize_designation(value: str) -> str:
    value = "-".join(value.strip().upper().split())
    return re.sub(r"^CS-(\w+)-", r"CS-\1.", value)
