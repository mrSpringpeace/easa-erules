"""SQLite connection and schema for the local search index (FTS5)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS index_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_key    TEXT NOT NULL UNIQUE,
    document_id     TEXT NOT NULL,
    title           TEXT,
    authority       TEXT,
    version         TEXT,
    source_path     TEXT,
    source_sha256   TEXT NOT NULL,
    parser_version  TEXT NOT NULL,
    indexed_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_rowid  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    node_id         TEXT NOT NULL,
    designation     TEXT,
    erules_id       TEXT,
    title           TEXT,
    topic_type      TEXT NOT NULL,
    text_content    TEXT NOT NULL DEFAULT '',
    metadata_json   TEXT NOT NULL DEFAULT '{}',
    UNIQUE(document_rowid, node_id)
);

CREATE TABLE IF NOT EXISTS paragraphs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    document_rowid  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    topic_rowid     INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    node_id         TEXT NOT NULL,
    text_content    TEXT NOT NULL DEFAULT '',
    UNIQUE(document_rowid, node_id)
);

CREATE TABLE IF NOT EXISTS references_idx (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    document_rowid      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    source_node_id      TEXT,
    target_designation  TEXT,
    target_id           TEXT,
    raw_text            TEXT,
    resolved            INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS assets_idx (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    document_rowid      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    deterministic_name  TEXT NOT NULL,
    content_type        TEXT,
    sha256              TEXT,
    size                INTEGER
);

-- FTS5: full-text search over topics (title + body)
CREATE VIRTUAL TABLE IF NOT EXISTS topics_fts USING fts5(
    designation,
    title,
    text_content,
    topic_type,
    content='topics',
    content_rowid='id',
    tokenize='porter unicode61'
);

-- Keep FTS in sync with topics
CREATE TRIGGER IF NOT EXISTS topics_ai AFTER INSERT ON topics BEGIN
    INSERT INTO topics_fts(rowid, designation, title, text_content, topic_type)
    VALUES (new.id, new.designation, new.title, new.text_content, new.topic_type);
END;

CREATE TRIGGER IF NOT EXISTS topics_ad AFTER DELETE ON topics BEGIN
    INSERT INTO topics_fts(topics_fts, rowid, designation, title, text_content, topic_type)
    VALUES ('delete', old.id, old.designation, old.title, old.text_content, old.topic_type);
END;

CREATE TRIGGER IF NOT EXISTS topics_au AFTER UPDATE ON topics BEGIN
    INSERT INTO topics_fts(topics_fts, rowid, designation, title, text_content, topic_type)
    VALUES ('delete', old.id, old.designation, old.title, old.text_content, old.topic_type);
    INSERT INTO topics_fts(rowid, designation, title, text_content, topic_type)
    VALUES (new.id, new.designation, new.title, new.text_content, new.topic_type);
END;

-- FTS5 over paragraphs
CREATE VIRTUAL TABLE IF NOT EXISTS paragraphs_fts USING fts5(
    text_content,
    content='paragraphs',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS paragraphs_ai AFTER INSERT ON paragraphs BEGIN
    INSERT INTO paragraphs_fts(rowid, text_content)
    VALUES (new.id, new.text_content);
END;

CREATE TRIGGER IF NOT EXISTS paragraphs_ad AFTER DELETE ON paragraphs BEGIN
    INSERT INTO paragraphs_fts(paragraphs_fts, rowid, text_content)
    VALUES ('delete', old.id, old.text_content);
END;

CREATE TRIGGER IF NOT EXISTS paragraphs_au AFTER UPDATE ON paragraphs BEGIN
    INSERT INTO paragraphs_fts(paragraphs_fts, rowid, text_content)
    VALUES ('delete', old.id, old.text_content);
    INSERT INTO paragraphs_fts(rowid, text_content)
    VALUES (new.id, new.text_content);
END;
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open (and create) a search index database with schema applied."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # FTS5 is part of the standard Python sqlite3 build on almost all platforms
    conn.executescript(SCHEMA_SQL)
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM index_meta WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO index_meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
