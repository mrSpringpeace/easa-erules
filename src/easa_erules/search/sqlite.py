"""SQLite connection and schema v2 for a version-specific FTS5 index."""

from __future__ import annotations

import sqlite3
from pathlib import Path

INDEX_SCHEMA_VERSION = "2"

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
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    document_rowid      INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    node_id             TEXT NOT NULL,
    designation         TEXT,
    erules_id           TEXT,
    title               TEXT,
    topic_type          TEXT NOT NULL,
    ordinal             INTEGER NOT NULL,
    material_category   TEXT,
    structure_kind      TEXT,
    has_table           INTEGER NOT NULL DEFAULT 0,
    has_figure          INTEGER NOT NULL DEFAULT 0,
    is_definition       INTEGER NOT NULL DEFAULT 0,
    path_text           TEXT NOT NULL DEFAULT '',
    path_json           TEXT NOT NULL DEFAULT '[]',
    plain_text          TEXT NOT NULL DEFAULT '',
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    UNIQUE(document_rowid, node_id)
);

CREATE TABLE IF NOT EXISTS topic_ancestors (
    topic_rowid      INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    ancestor_node_id TEXT NOT NULL,
    depth            INTEGER NOT NULL,
    PRIMARY KEY(topic_rowid, ancestor_node_id)
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

CREATE INDEX IF NOT EXISTS topics_material_category_idx ON topics(material_category);
CREATE INDEX IF NOT EXISTS topics_structure_kind_idx ON topics(structure_kind);
CREATE INDEX IF NOT EXISTS topics_features_idx ON topics(has_table, has_figure);
CREATE INDEX IF NOT EXISTS topic_ancestors_node_idx ON topic_ancestors(ancestor_node_id);

CREATE VIRTUAL TABLE IF NOT EXISTS topics_fts USING fts5(
    designation,
    title,
    plain_text,
    content='topics',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS topics_ai AFTER INSERT ON topics BEGIN
    INSERT INTO topics_fts(rowid, designation, title, plain_text)
    VALUES (new.id, new.designation, new.title, new.plain_text);
END;

CREATE TRIGGER IF NOT EXISTS topics_ad AFTER DELETE ON topics BEGIN
    INSERT INTO topics_fts(topics_fts, rowid, designation, title, plain_text)
    VALUES ('delete', old.id, old.designation, old.title, old.plain_text);
END;

CREATE TRIGGER IF NOT EXISTS topics_au AFTER UPDATE ON topics BEGIN
    INSERT INTO topics_fts(topics_fts, rowid, designation, title, plain_text)
    VALUES ('delete', old.id, old.designation, old.title, old.plain_text);
    INSERT INTO topics_fts(rowid, designation, title, plain_text)
    VALUES (new.id, new.designation, new.title, new.plain_text);
END;
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open (and create) a search database with schema applied."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM index_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO index_meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
