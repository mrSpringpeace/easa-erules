"""Local search — SQLite FTS5 index and query."""

from .indexer import build_index, ensure_index, index_db_path
from .query import SearchHit, SearchResult, prepare_fts_query, search

__all__ = [
    "SearchHit",
    "SearchResult",
    "build_index",
    "ensure_index",
    "index_db_path",
    "prepare_fts_query",
    "search",
]
