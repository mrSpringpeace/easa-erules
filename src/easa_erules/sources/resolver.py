"""Resolve EASA publication download URLs.

Two inventories, in order of preference:

1. EASA's ``publication-history.xml`` (see :mod:`.history`), for catalog entries
   that carry ``ear_codes``. It lists every generation, not only the current
   one, with the publisher's MD5 and generation date.
2. The document's landing page, scraped for download links. Used when the
   entry has no ``ear_codes`` or the history cannot be read; the fallback is
   reported in ``ResolveResult.warnings``, never taken silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from lxml import html

from .history import (
    DEFAULT_USER_AGENT,
    PUBLICATION_HISTORY_URL,
    HistoryEntry,
    PublicationHistoryFormatError,
    entries_for_codes,
    parse_publication_history,
)
from .registry import get_source

__all__ = ["DEFAULT_USER_AGENT", "EasaSourceResolver", "Publication", "ResolveResult"]

INVENTORY_PUBLICATION_HISTORY = "publication_history"
INVENTORY_LANDING_PAGE = "landing_page"

#: publication-history.xml link type -> Publication.format. "xmlzip" is a ZIP
#: holding the Flat OPC XML, which this toolkit has always called "xml".
_HISTORY_LINK_FORMATS = {"xmlzip": "xml", "pdf": "pdf"}


@dataclass(slots=True)
class Publication:
    """A single downloadable publication found on a landing page."""

    title: str
    version_label: str
    version_slug: str
    format: str  # xml | pdf | other
    download_url: str
    content_type: str | None = None
    filename: str | None = None
    size: int | None = None
    link_text: str = ""
    # Set only for publications read from publication-history.xml.
    md5: str | None = None  # publisher's MD5 of the downloaded file (ZIP/PDF)
    generated_at: str | None = None  # ISO 8601 UTC generation date
    history_file_name: str | None = None  # <fileName>, unique per generation
    notes: str | None = None  # <notes> as published

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "version_label": self.version_label,
            "version_slug": self.version_slug,
            "format": self.format,
            "download_url": self.download_url,
            "content_type": self.content_type,
            "filename": self.filename,
            "size": self.size,
            "link_text": self.link_text,
            "md5": self.md5,
            "generated_at": self.generated_at,
            "history_file_name": self.history_file_name,
            "notes": self.notes,
        }


@dataclass(slots=True)
class ResolveResult:
    """Result of resolving a document's available publications."""

    document_id: str
    title: str
    landing_page: str
    publications: list[Publication] = field(default_factory=list)
    selected: Publication | None = None
    #: Where ``publications`` came from: "publication_history" | "landing_page".
    inventory: str = INVENTORY_LANDING_PAGE
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "landing_page": self.landing_page,
            "inventory": self.inventory,
            "warnings": list(self.warnings),
            "publications": [p.to_dict() for p in self.publications],
            "selected": self.selected.to_dict() if self.selected else None,
        }


class EasaSourceResolver:
    """Discover XML (and other) downloads from EASA Easy Access Rules landing pages."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        timeout: float = 60.0,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self._owns_client = client is None
        self.client = client or httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": user_agent},
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> EasaSourceResolver:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def resolve(
        self,
        doc_id: str,
        *,
        version: str | None = None,
        preferred_format: str | None = None,
    ) -> ResolveResult:
        """Open the landing page, list publications, select latest or pinned version."""
        source = get_source(doc_id)
        landing = source["landing_page"]
        # The catalog entry wins unless the caller asks for a specific format —
        # CS-ETSO is pdf-only, and a hardcoded "xml" default silently overrode it.
        preferred = preferred_format or source.get("preferred_format") or "xml"

        warnings: list[str] = []
        publications: list[Publication] = []
        inventory = INVENTORY_LANDING_PAGE
        ear_codes = [str(code) for code in source.get("ear_codes") or []]
        if ear_codes:
            try:
                publications = self.discover_history_publications(ear_codes)
            except (httpx.HTTPError, PublicationHistoryFormatError) as exc:
                warnings.append(
                    f"publication_history_unavailable: {exc}; fell back to the landing page"
                )
            else:
                if publications:
                    inventory = INVENTORY_PUBLICATION_HISTORY
                else:
                    warnings.append(
                        f"publication_history_has_no_entries for ear_codes {ear_codes}; "
                        "fell back to the landing page"
                    )
        if inventory == INVENTORY_LANDING_PAGE:
            publications = self.discover_publications(landing)

        selected = self.select_publication(
            publications,
            version=version,
            preferred_format=preferred,
        )

        return ResolveResult(
            document_id=source["id"],
            title=source.get("title") or source["id"],
            landing_page=landing,
            publications=publications,
            selected=selected,
            inventory=inventory,
            warnings=warnings,
        )

    def discover_history_publications(self, ear_codes: list[str]) -> list[Publication]:
        """Fetch publication-history.xml and list the generations of *ear_codes*."""
        response = self.client.get(PUBLICATION_HISTORY_URL)
        response.raise_for_status()
        entries = parse_publication_history(response.content, base_url=str(response.url))
        return publications_from_history(entries_for_codes(entries, ear_codes))

    def discover_publications(self, landing_page: str) -> list[Publication]:
        """Fetch a landing page and extract downloadable publications."""
        response = self.client.get(landing_page)
        response.raise_for_status()
        return parse_landing_page_publications(response.text, base_url=str(response.url))

    def select_publication(
        self,
        publications: list[Publication],
        *,
        version: str | None = None,
        preferred_format: str = "xml",
    ) -> Publication | None:
        """Pick a publication by format preference and optional version pin."""
        if not publications:
            return None

        preferred = preferred_format.lower()
        candidates = [p for p in publications if p.format == preferred]
        if not candidates:
            # Falling back to another format looks like success and fails a
            # layer down with a confusing message: CS-ETSO is PDF-only, and a
            # PDF selected as "the XML" reaches the OOXML reader as garbage.
            available = ", ".join(sorted({p.format for p in publications})) or "none"
            raise LookupError(
                f"No {preferred!r} publication on this landing page "
                f"(available formats: {available})"
            )

        if version:
            needle = _slugify_version(version)
            # Narrowest match first. A substring test alone picks "amendment-10"
            # for "amendment-1" once the history lists both.
            exact = [
                p
                for p in candidates
                if needle in (p.version_slug, _slugify_version(p.version_label))
            ]
            prefix = [p for p in candidates if p.version_slug.startswith(needle + "-")]
            # Anywhere in slug, label or title, but only on whole "-" tokens.
            bounded = re.compile(rf"(?:^|-){re.escape(needle)}(?:-|$)")
            loose = [
                p
                for p in candidates
                if bounded.search(p.version_slug)
                or bounded.search(_slugify_version(p.version_label))
                or bounded.search(_slugify_version(p.title))
            ]
            matched = exact or prefix or loose
            if not matched:
                raise LookupError(
                    f"No publication matching version '{version}'. "
                    f"Available: {', '.join(sorted({p.version_label for p in publications}))}"
                )
            slugs = sorted({p.version_slug for p in matched})
            if len(slugs) > 1:
                raise LookupError(
                    f"Version '{version}' is ambiguous; it matches {', '.join(slugs)}. "
                    "Pass one of these exactly."
                )
            # Several generations of one version: the newest one.
            return max(matched, key=_publication_sort_key)

        # Latest: prefer XML, then highest sort key (amendment number)
        return max(candidates, key=_publication_sort_key)


def parse_landing_page_publications(html_text: str, base_url: str) -> list[Publication]:
    """Parse download anchors from an EASA landing page HTML body."""
    tree = html.fromstring(html_text)
    pubs: list[Publication] = []
    seen_urls: set[str] = set()

    anchors = tree.xpath(
        '//a[contains(@class,"matomo_download") or contains(@href,"/downloads/")]'
    )
    for anchor in anchors:
        href = anchor.get("href") or ""
        if not href or href.startswith("#"):
            continue
        url = urljoin(base_url, href)
        if url in seen_urls:
            continue

        title_attr = (anchor.get("title") or "").strip()
        link_text = " ".join((anchor.text_content() or "").split())
        content_type = (anchor.get("type") or "").strip() or None
        size = _parse_size_from_type(content_type)

        fmt = _detect_format(title_attr, link_text, content_type, url)
        # Skip non-document site chrome links without a useful type/title
        if fmt == "other" and not title_attr and "/downloads/" not in href:
            continue

        # Prefer visible link text for human version labels; fall back to filename title
        version_label = (
            _extract_version_label(link_text)
            or _extract_version_label(title_attr)
            or ""
        )
        version_slug = _slugify_version(
            version_label or link_text or title_attr or "unknown"
        )
        filename = _filename_from_title(title_attr) or _filename_from_url(url)

        display_title = link_text or title_attr or filename or url

        # Prefer entries that look like real EAR downloads
        if fmt == "other" and not re.search(r"easy.?access|cs[- ]|/en/downloads/", display_title + url, re.IGNORECASE):
            continue

        seen_urls.add(url)
        pubs.append(
            Publication(
                title=display_title,
                version_label=version_label or "unknown",
                version_slug=version_slug,
                format=fmt,
                download_url=url,
                content_type=content_type,
                filename=filename,
                size=size,
                link_text=link_text,
            )
        )

    return pubs


def _detect_format(title: str, text: str, content_type: str | None, url: str) -> str:
    blob = " ".join([title, text, content_type or "", url]).lower()
    if "(xml)" in blob or blob.endswith(".xml") or "xml)" in blob:
        return "xml"
    if "application/zip" in blob or blob.endswith(".zip"):
        # EASA ships Flat OPC XML inside zip; treat as xml when labelled XML
        if "xml" in blob:
            return "xml"
        return "zip"
    if "application/pdf" in blob or blob.endswith(".pdf") or "(pdf)" in blob:
        return "pdf"
    if "/downloads/" in blob and "xml" in blob:
        return "xml"
    return "other"


def _extract_version_label(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r"(Amendment\s+\d+(?:\s*/\s*Issue\s+\d+)?)",
        r"(Amdt\.?[\s_-]*\d+)",
        r"(Initial\s+issue)",
        r"(Issue\s+\d+)",
        r"(CS\d+-AMC\d+)",  # e.g. CS6-AMC5 style pins
        r"(Revision\s+\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            label = match.group(1)
            # Normalize Amdt / amdt_1 → Amendment N
            label = re.sub(
                r"^Amdt\.?[\s_-]*",
                "Amendment ",
                label,
                flags=re.IGNORECASE,
            )
            return " ".join(label.split())
    return ""


def _slugify_version(text: str) -> str:
    text = text.strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^\w\s.-]+", "", text)
    text = re.sub(r"[\s._]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "unknown"


def _publication_sort_key(pub: Publication) -> tuple[int, str, int, int, int, str]:
    """Higher is newer.

    History publications carry their generation date, which orders them
    exactly. Landing-page publications have none ("" for all), so for them the
    amendment/issue numbers decide, as before.
    """
    label = pub.version_label.lower()
    amdt = re.search(r"(?:amendment|amdt)\s*(\d+)", label)
    issue = re.search(r"issue\s*(\d+)", label)
    amdt_n = int(amdt.group(1)) if amdt else -1
    issue_n = int(issue.group(1)) if issue else -1
    is_initial = 0 if "initial" in label else 1
    fmt_score = 2 if pub.format == "xml" else 1 if pub.format == "zip" else 0
    return (fmt_score, pub.generated_at or "", is_initial, amdt_n, issue_n, pub.title)


def _parse_size_from_type(content_type: str | None) -> int | None:
    if not content_type:
        return None
    match = re.search(r"length=(\d+)", content_type)
    return int(match.group(1)) if match else None


def _filename_from_title(title: str) -> str | None:
    if title and re.search(r"\.(pdf|zip|xml)$", title, re.IGNORECASE):
        return title.split("/")[-1]
    return None


def _filename_from_url(url: str) -> str | None:
    path = urlparse(url).path
    name = path.rstrip("/").split("/")[-1]
    if "." in name:
        return name
    return None


def history_version_label(notes: str) -> str:
    """Version label for a publication-history ``<notes>`` text.

    - "CS Amendment 6, AMC/GM Issue 5" -> "Amendment 6 / Issue 5". CS-23 has
      two generations of CS Amendment 6 with different AMC/GM issues (4 and 5);
      both numbers are needed to tell them apart.
    - "Amentment 2" (CS-25, as published) -> "Amendment 2".
    - Amendment / Issue / Initial issue -> as :func:`_extract_version_label`.
    - Anything else ("Revision from November 2025") is kept verbatim.
    """
    text = " ".join(notes.split())
    combined = re.fullmatch(r"CS Amendment (\d+), AMC/GM Issue (\d+)", text, flags=re.IGNORECASE)
    if combined:
        return f"Amendment {combined.group(1)} / Issue {combined.group(2)}"
    text = re.sub(r"\bAmentment\b", "Amendment", text, flags=re.IGNORECASE)
    return _extract_version_label(text) or text or "unknown"


def publications_from_history(entries: list[HistoryEntry]) -> list[Publication]:
    """One Publication per link of each history entry, in the given order."""
    pubs: list[Publication] = []
    for entry in entries:
        label = history_version_label(entry.notes)
        for link in entry.links:
            pubs.append(
                Publication(
                    title=f"{entry.ear_name} ({entry.notes or 'no notes'})",
                    version_label=label,
                    version_slug=_slugify_version(label),
                    format=_HISTORY_LINK_FORMATS.get(link.link_type, "other"),
                    download_url=link.url,
                    filename=_filename_from_url(link.url),
                    md5=link.md5,
                    generated_at=entry.generated_at,
                    history_file_name=entry.file_name,
                    notes=entry.notes,
                )
            )
    return pubs
