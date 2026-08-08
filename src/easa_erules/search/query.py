"""Query the local SQLite FTS5 search index."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .sqlite import connect


@dataclass(slots=True)
class SearchHit:
    """A single search result (topic-level)."""

    designation: str
    erules_id: str
    title: str
    topic_type: str
    node_id: str
    snippet: str
    rank: float
    text_preview: str = ""
    match_source: str = "topic"  # topic | paragraph

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
        }


@dataclass(slots=True)
class SearchResult:
    """Search response for a document."""

    document_key: str
    document_id: str
    title: str
    query: str
    hits: list[SearchHit] = field(default_factory=list)
    total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "document": {
                "key": self.document_key,
                "id": self.document_id,
                "title": self.title,
            },
            "query": self.query,
            "total": self.total,
            "hits": [h.to_dict() for h in self.hits],
        }


def prepare_fts_query(user_query: str) -> str:
    """Convert a user query into a safe FTS5 MATCH expression.

    - Strips FTS special characters that break MATCH
    - Multi-word queries become AND of prefix-friendly tokens
    - Quoted phrases are preserved
    """
    q = user_query.strip()
    if not q:
        return ""

    # Keep quoted phrases
    phrases: list[str] = []
    def _keep_phrase(m: re.Match[str]) -> str:
        phrases.append(m.group(1))
        return f" __PHRASE{len(phrases) - 1}__ "

    q = re.sub(r'"([^"]+)"', _keep_phrase, q)

    # Remove FTS operators the user likely didn't mean as syntax
    q = re.sub(r"[^\w\s\-./]", " ", q, flags=re.UNICODE)
    tokens = [t for t in q.split() if t and not t.startswith("__PHRASE")]

    parts: list[str] = []
    for i, phrase in enumerate(phrases):
        parts.append(f'"{phrase}"')
    for tok in tokens:
        # Escape double quotes inside token
        safe = tok.replace('"', '""')
        parts.append(f'"{safe}"')

    return " AND ".join(parts) if parts else ""


def search(
    db_path: Path | str,
    query: str,
    *,
    limit: int = 20,
    document_key: str | None = None,
) -> SearchResult:
    """Run an FTS5 search and return ranked topic hits."""
    fts_q = prepare_fts_query(query)
    conn = connect(db_path)
    try:
        doc_row = _select_document(conn, document_key)
        if not doc_row:
            return SearchResult(
                document_key=document_key or "",
                document_id="",
                title="",
                query=query,
                hits=[],
                total=0,
            )

        if not fts_q:
            return SearchResult(
                document_key=doc_row["document_key"],
                document_id=doc_row["document_id"],
                title=doc_row["title"] or "",
                query=query,
                hits=[],
                total=0,
            )

        hits = _search_topics(conn, doc_row["id"], fts_q, limit=limit)

        # Supplement with paragraph matches not already covered
        if len(hits) < limit:
            para_hits = _search_paragraphs(
                conn,
                doc_row["id"],
                fts_q,
                limit=limit - len(hits),
                exclude_node_ids={h.node_id for h in hits},
            )
            hits.extend(para_hits)

        return SearchResult(
            document_key=doc_row["document_key"],
            document_id=doc_row["document_id"],
            title=doc_row["title"] or "",
            query=query,
            hits=hits,
            total=len(hits),
        )
    finally:
        conn.close()


def _select_document(
    conn: sqlite3.Connection,
    document_key: str | None,
) -> sqlite3.Row | None:
    if document_key:
        return conn.execute(
            "SELECT * FROM documents WHERE document_key = ?",
            (document_key.lower(),),
        ).fetchone()
    return conn.execute(
        "SELECT * FROM documents ORDER BY id DESC LIMIT 1"
    ).fetchone()


def _search_topics(
    conn: sqlite3.Connection,
    document_rowid: int,
    fts_q: str,
    *,
    limit: int,
) -> list[SearchHit]:
    rows = conn.execute(
        """
        SELECT
            t.node_id,
            t.designation,
            t.erules_id,
            t.title,
            t.topic_type,
            t.text_content,
            snippet(topics_fts, 2, '«', '»', '…', 24) AS snip,
            bm25(topics_fts) AS score
        FROM topics_fts
        JOIN topics t ON t.id = topics_fts.rowid
        WHERE topics_fts MATCH ?
          AND t.document_rowid = ?
        ORDER BY score
        LIMIT ?
        """,
        (fts_q, document_rowid, limit),
    ).fetchall()

    hits: list[SearchHit] = []
    for row in rows:
        preview = (row["text_content"] or "")[:280]
        hits.append(
            SearchHit(
                designation=row["designation"] or "",
                erules_id=row["erules_id"] or "",
                title=row["title"] or "",
                topic_type=row["topic_type"] or "",
                node_id=row["node_id"] or "",
                snippet=row["snip"] or preview,
                rank=float(row["score"] or 0.0),
                text_preview=preview,
                match_source="topic",
            )
        )
    return hits


def _search_paragraphs(
    conn: sqlite3.Connection,
    document_rowid: int,
    fts_q: str,
    *,
    limit: int,
    exclude_node_ids: set[str],
) -> list[SearchHit]:
    rows = conn.execute(
        """
        SELECT
            t.node_id AS topic_node_id,
            t.designation,
            t.erules_id,
            t.title,
            t.topic_type,
            p.text_content,
            snippet(paragraphs_fts, 0, '«', '»', '…', 24) AS snip,
            bm25(paragraphs_fts) AS score
        FROM paragraphs_fts
        JOIN paragraphs p ON p.id = paragraphs_fts.rowid
        LEFT JOIN topics t ON t.id = p.topic_rowid
        WHERE paragraphs_fts MATCH ?
          AND p.document_rowid = ?
        ORDER BY score
        LIMIT ?
        """,
        (fts_q, document_rowid, limit * 3),
    ).fetchall()

    hits: list[SearchHit] = []
    seen: set[str] = set(exclude_node_ids)
    for row in rows:
        node_id = row["topic_node_id"] or ""
        if node_id in seen:
            continue
        seen.add(node_id)
        preview = (row["text_content"] or "")[:280]
        hits.append(
            SearchHit(
                designation=row["designation"] or "",
                erules_id=row["erules_id"] or "",
                title=row["title"] or "",
                topic_type=row["topic_type"] or "paragraph",
                node_id=node_id,
                snippet=row["snip"] or preview,
                rank=float(row["score"] or 0.0),
                text_preview=preview,
                match_source="paragraph",
            )
        )
        if len(hits) >= limit:
            break
    return hits
