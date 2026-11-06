"""EASA Easy Access Rules publication history (``publication-history.xml``).

On 2026-11-05 EASA started publishing one machine-readable file that lists
every EAR generation it has put out, by domain, with a download link and an
MD5 per file:

    https://www.easa.europa.eu/gcs/files/publication-history.xml

This module reads that file. It does not choose versions or download
publications; the resolver and downloader do that on top of it.

What the file looks like (observed 2026-11-06, no XSD is published for it):

    <XML>
      <Title>EASA Easy Access Rules (EAR) Downloads</Title>
      <Domain>
        <Name>Initial Airworthiness and Environmental Protection</Name>
        <file>
          <id>…</id>                       unique only inside its Domain
          <fileName>FE9752_2022-06-28_07.52.05_EAR-for-Very-Light-Aeroplanes-CS-VLA</fileName>
          <earName>Easy Access Rules for Very Light Aeroplanes (CS-VLA)</earName>
          <links>
            <link type="xmlzip" md5="…">/en/gcs/files/FE9752_….zip</link>
          </links>
          <date>2022-06-28T07:52:05Z</date>
          <notes>Amendment 1</notes>
        </file>

Facts the code below relies on, each checked against the 2026-11-06 copy:

- The six-character prefix of ``fileName`` (the *EAR code*) is the same for
  every generation of one publication. It is the only stable key: ``earName``
  varies by whitespace (``95CADA`` appears with and without a no-break space)
  and Part-21 is spread over two codes (``450F3E`` and ``313A4D``).
- One entry is one *generation*, not one amendment. The same ``notes`` can
  appear on several entries (CS-29 "Amendment 10" as XML on 2022-12-19 and as
  PDF on 2022-12-20), and ``notes`` is free text with typos ("Amentment 2").
- ``date`` and the timestamp inside ``fileName`` can differ; ``date`` is used.
  The ``fileName`` time is ``HH.MM.SS`` in 295 of 296 entries and ``HH.MM`` in
  one (``D77B75_2018-11-20_18.51_…``, CS-ETSO Amendment 2); both are accepted.

Anything that does not fit this shape raises :class:`PublicationHistoryFormatError`
instead of being skipped: a quietly shorter version list is the failure mode
this toolkit exists to prevent.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
import yaml
from lxml import etree

from .cache import default_cache_root
from .resolver import DEFAULT_USER_AGENT

PUBLICATION_HISTORY_URL = "https://www.easa.europa.eu/gcs/files/publication-history.xml"

#: Cache directory name under the cache root. The leading underscore keeps it
#: out of the document id space (catalog ids never start with one).
HISTORY_CACHE_DIRNAME = "_publication-history"

_FILE_NAME = re.compile(
    r"(?P<code>[0-9A-F]{6})_(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}\.\d{2}(?:\.\d{2})?)_(?P<slug>.+)\Z"
)
_MD5 = re.compile(r"[0-9a-f]{32}\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


class PublicationHistoryFormatError(ValueError):
    """The history file does not have the structure this module was written for."""


@dataclass(frozen=True, slots=True)
class HistoryLink:
    """One downloadable file of one generation."""

    link_type: str  # as published: "xmlzip" | "pdf" (others are kept verbatim)
    url: str  # absolute
    md5: str  # lowercase hex, as published by EASA

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.link_type, "url": self.url, "md5": self.md5}


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """One published generation of one Easy Access Rules document."""

    domain: str
    ear_code: str
    file_name: str
    ear_name: str  # whitespace-normalised
    generated_at: str  # ISO 8601 UTC, from <date>
    notes: str  # free text as published, whitespace-normalised
    links: tuple[HistoryLink, ...]

    def link(self, link_type: str) -> HistoryLink | None:
        """The link of *link_type*, or ``None`` when this generation has none."""
        for candidate in self.links:
            if candidate.link_type == link_type:
                return candidate
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "ear_code": self.ear_code,
            "file_name": self.file_name,
            "ear_name": self.ear_name,
            "generated_at": self.generated_at,
            "notes": self.notes,
            "links": [link.to_dict() for link in self.links],
        }


def parse_publication_history(
    xml_bytes: bytes,
    *,
    base_url: str = PUBLICATION_HISTORY_URL,
) -> list[HistoryEntry]:
    """Parse ``publication-history.xml`` into entries, in document order.

    Raises :class:`PublicationHistoryFormatError` on any structural surprise.
    """
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        root = etree.fromstring(xml_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise PublicationHistoryFormatError(f"Not well-formed XML: {exc}") from exc

    if root.tag != "XML":
        raise PublicationHistoryFormatError(f"Root element is {root.tag!r}, expected 'XML'")

    domains = root.findall("Domain")
    if not domains:
        raise PublicationHistoryFormatError("No <Domain> elements")

    entries: list[HistoryEntry] = []
    for domain in domains:
        domain_name = _required_text(domain, "Name", "Domain")
        files = domain.findall("file")
        if not files:
            raise PublicationHistoryFormatError(f"Domain {domain_name!r} has no <file> elements")
        for file_el in files:
            entries.append(_parse_file(file_el, domain_name, base_url))
    return entries


def _parse_file(file_el: etree._Element, domain_name: str, base_url: str) -> HistoryEntry:
    file_name = _required_text(file_el, "fileName", f"file in {domain_name!r}")
    where = f"file {file_name!r}"
    match = _FILE_NAME.match(file_name)
    if match is None:
        raise PublicationHistoryFormatError(
            f"{where}: fileName does not match CODE_YYYY-MM-DD_HH.MM[.SS]_title"
        )

    generated_at = _required_text(file_el, "date", where)
    if not _DATE.match(generated_at):
        raise PublicationHistoryFormatError(f"{where}: date {generated_at!r} is not YYYY-MM-DDTHH:MM:SSZ")

    link_elements = file_el.findall("links/link")
    if not link_elements:
        raise PublicationHistoryFormatError(f"{where}: no <links>/<link>")
    links: list[HistoryLink] = []
    for link_el in link_elements:
        link_type = (link_el.get("type") or "").strip()
        md5 = (link_el.get("md5") or "").strip().lower()
        href = _normalise(link_el.text)
        if not link_type or not href:
            raise PublicationHistoryFormatError(f"{where}: <link> without type or URL")
        if not _MD5.match(md5):
            raise PublicationHistoryFormatError(f"{where}: <link type={link_type!r}> md5 {md5!r} is not 32 hex digits")
        links.append(HistoryLink(link_type=link_type, url=urljoin(base_url, href), md5=md5))

    return HistoryEntry(
        domain=domain_name,
        ear_code=match.group("code"),
        file_name=file_name,
        ear_name=_required_text(file_el, "earName", where),
        generated_at=generated_at,
        # Empty notes are allowed: the label is then simply unknown.
        notes=_normalise(file_el.findtext("notes")),
        links=tuple(links),
    )


def _required_text(parent: etree._Element, tag: str, where: str) -> str:
    text = _normalise(parent.findtext(tag))
    if not text:
        raise PublicationHistoryFormatError(f"{where}: missing or empty <{tag}>")
    return text


def _normalise(text: str | None) -> str:
    """Collapse whitespace, including the no-break spaces EASA uses in names."""
    return " ".join((text or "").replace(" ", " ").split())


def entries_for_codes(entries: list[HistoryEntry], ear_codes: list[str]) -> list[HistoryEntry]:
    """Entries whose EAR code is in *ear_codes*, newest generation first."""
    wanted = {code.upper() for code in ear_codes}
    selected = [entry for entry in entries if entry.ear_code in wanted]
    return sorted(selected, key=lambda entry: (entry.generated_at, entry.file_name), reverse=True)


# --- cache ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HistorySnapshot:
    """A cached copy of the history file and where it came from."""

    entries: list[HistoryEntry]
    path: Path
    sha256: str
    retrieved_at: str
    url: str


def history_cache_dir(cache_root: Path | None = None) -> Path:
    return (cache_root or default_cache_root()) / HISTORY_CACHE_DIRNAME


def fetch_publication_history(
    *,
    cache_root: Path | None = None,
    client: httpx.Client | None = None,
    url: str = PUBLICATION_HISTORY_URL,
) -> HistorySnapshot:
    """Download the history file, parse it, then write it to the cache.

    The file is parsed *before* it replaces the cached copy, so a malformed
    download never overwrites a good one.
    """
    owns_client = client is None
    http = client or httpx.Client(
        follow_redirects=True, timeout=60.0, headers={"User-Agent": DEFAULT_USER_AGENT}
    )
    try:
        response = http.get(url)
        response.raise_for_status()
        body = response.content
    finally:
        if owns_client:
            http.close()

    entries = parse_publication_history(body, base_url=url)

    target_dir = history_cache_dir(cache_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    xml_path = target_dir / "publication-history.xml"
    sha256 = hashlib.sha256(body).hexdigest()
    retrieved_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    xml_path.write_bytes(body)
    meta = {
        "url": url,
        "retrieved_at": retrieved_at,
        "sha256": sha256,
        "size": len(body),
        "entry_count": len(entries),
    }
    (target_dir / "meta.yaml").write_text(yaml.safe_dump(meta, sort_keys=False), encoding="utf-8")
    return HistorySnapshot(entries, xml_path, sha256, retrieved_at, url)


def load_cached_publication_history(cache_root: Path | None = None) -> HistorySnapshot | None:
    """The cached history, or ``None`` when it was never fetched.

    A cached file whose bytes no longer match the stored SHA-256 raises
    ``ValueError`` rather than being trusted or silently refetched.
    """
    target_dir = history_cache_dir(cache_root)
    xml_path = target_dir / "publication-history.xml"
    meta_path = target_dir / "meta.yaml"
    if not xml_path.is_file() or not meta_path.is_file():
        return None
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    body = xml_path.read_bytes()
    actual = hashlib.sha256(body).hexdigest()
    expected = str(meta.get("sha256") or "")
    if expected != actual:
        raise ValueError(
            f"Cached publication history SHA-256 mismatch: expected {expected or 'none'}, got {actual}"
        )
    entries = parse_publication_history(body, base_url=str(meta.get("url") or PUBLICATION_HISTORY_URL))
    return HistorySnapshot(
        entries, xml_path, actual, str(meta.get("retrieved_at") or ""), str(meta.get("url") or "")
    )
