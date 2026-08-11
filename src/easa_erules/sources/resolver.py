"""Resolve EASA publication download URLs from stable landing pages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from lxml import html

from .. import __version__
from .registry import get_source

DEFAULT_USER_AGENT = f"easa-erules/{__version__} (+https://github.com/mrSpringpeace/easa-erules)"


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
        }


@dataclass(slots=True)
class ResolveResult:
    """Result of resolving a document's available publications."""

    document_id: str
    title: str
    landing_page: str
    publications: list[Publication] = field(default_factory=list)
    selected: Publication | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "landing_page": self.landing_page,
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
        )

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
            for pub in candidates:
                if (
                    needle == pub.version_slug
                    or needle in pub.version_slug
                    or needle in _slugify_version(pub.version_label)
                    or needle in _slugify_version(pub.title)
                    or version.lower() in pub.title.lower()
                    or version.lower() in pub.version_label.lower()
                ):
                    return pub
            raise LookupError(
                f"No publication matching version '{version}'. "
                f"Available: {', '.join(sorted({p.version_label for p in publications}))}"
            )

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


def _publication_sort_key(pub: Publication) -> tuple[int, int, int, int, str]:
    """Higher is newer. Prefer amendment numbers, then initial issue last."""
    label = pub.version_label.lower()
    amdt = re.search(r"(?:amendment|amdt)\s*(\d+)", label)
    issue = re.search(r"issue\s*(\d+)", label)
    amdt_n = int(amdt.group(1)) if amdt else -1
    issue_n = int(issue.group(1)) if issue else -1
    is_initial = 0 if "initial" in label else 1
    fmt_score = 2 if pub.format == "xml" else 1 if pub.format == "zip" else 0
    return (fmt_score, is_initial, amdt_n, issue_n, pub.title)


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
