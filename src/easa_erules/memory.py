"""Thread-safe bounded memory cache for parsed documents."""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from pathlib import Path

from . import __version__
from .parser import ParseResult
from .parsing import parse_any

_DEFAULT_MAXSIZE = 3
_lock = threading.RLock()
_cache: OrderedDict[tuple[str, int, int, str], ParseResult] = OrderedDict()


def _maxsize() -> int:
    try:
        return max(1, int(os.environ.get("EASA_ERULES_PARSE_CACHE_SIZE", _DEFAULT_MAXSIZE)))
    except ValueError:
        return _DEFAULT_MAXSIZE


def _key(path: Path) -> tuple[str, int, int, str]:
    resolved = path.resolve()
    stat = resolved.stat()
    return (str(resolved), stat.st_mtime_ns, stat.st_size, __version__)


def parse_cached(path: Path | str) -> ParseResult:
    """Parse *path* once per stable file identity and retain at most 3 results."""
    source = Path(path)
    key = _key(source)
    with _lock:
        existing = _cache.get(key)
        if existing is not None:
            _cache.move_to_end(key)
            return existing

    # Parsing is intentionally outside the lock. A concurrent duplicate parse
    # is preferable to blocking unrelated cached document reads for seconds.
    parsed = parse_any(source)
    with _lock:
        existing = _cache.get(key)
        if existing is not None:
            _cache.move_to_end(key)
            return existing
        # Remove obsolete identities for the same absolute path.
        for old_key in [item for item in _cache if item[0] == key[0]]:
            _cache.pop(old_key, None)
        _cache[key] = parsed
        while len(_cache) > _maxsize():
            _cache.popitem(last=False)
    return parsed


def clear_memory_cache(path: Path | str | None = None) -> None:
    """Clear every cached parse, or every identity belonging to one path."""
    with _lock:
        if path is None:
            _cache.clear()
            return
        resolved = str(Path(path).resolve())
        for key in [item for item in _cache if item[0] == resolved]:
            _cache.pop(key, None)


def memory_cache_info() -> dict[str, int]:
    """Small diagnostic snapshot useful to service health checks and tests."""
    with _lock:
        return {"size": len(_cache), "maxsize": _maxsize()}
