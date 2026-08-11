"""Sources package — registry, resolver, downloader, cache."""

from .cache import default_cache_root
from .downloader import CachedIntegrityError, EasaDownloader, FetchResult, resolve_local_source
from .inventory import CachedVersion, list_cached_version_records, resolve_cached_version
from .provenance import SourceProvenance, build_provenance
from .registry import REGISTRY, clear_registry_cache, get_source, list_sources, resolve_source_id
from .resolver import EasaSourceResolver, Publication, ResolveResult

__all__ = [
    "REGISTRY",
    "EasaDownloader",
    "EasaSourceResolver",
    "FetchResult",
    "CachedVersion",
    "CachedIntegrityError",
    "Publication",
    "ResolveResult",
    "SourceProvenance",
    "build_provenance",
    "clear_registry_cache",
    "default_cache_root",
    "get_source",
    "list_sources",
    "list_cached_version_records",
    "resolve_local_source",
    "resolve_source_id",
    "resolve_cached_version",
]
