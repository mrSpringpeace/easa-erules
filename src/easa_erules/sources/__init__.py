"""Sources package — registry, resolver, downloader, cache."""

from .cache import default_cache_root
from .downloader import EasaDownloader, FetchResult, resolve_local_source
from .registry import REGISTRY, clear_registry_cache, get_source, list_sources, resolve_source_id
from .resolver import EasaSourceResolver, Publication, ResolveResult

__all__ = [
    "REGISTRY",
    "EasaDownloader",
    "EasaSourceResolver",
    "FetchResult",
    "Publication",
    "ResolveResult",
    "clear_registry_cache",
    "default_cache_root",
    "get_source",
    "list_sources",
    "resolve_local_source",
    "resolve_source_id",
]
