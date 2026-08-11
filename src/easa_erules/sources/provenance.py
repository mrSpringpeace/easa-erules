"""Which regulation, at which amendment, from which file.

A quoted requirement is only worth something if the reader can get back to the
exact publication it came from. This module assembles that tuple once, so
``extract``, ``query``, ``refs`` and the Markdown frontmatter all state it the
same way.

Where issue or amendment cannot be established, the field says ``unknown`` and
a warning is emitted. It is never silently left empty: an agent that sees no
amendment must be able to tell "not applicable" from "nobody knows".
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

UNKNOWN = "unknown"

_AMENDMENT_RE = re.compile(r"\bAmendment\s+(\d+)\b", re.IGNORECASE)
_ISSUE_RE = re.compile(r"\bIssue\s+(\d+)\b", re.IGNORECASE)
_INITIAL_RE = re.compile(r"\bInitial\s+issue\b", re.IGNORECASE)


@dataclass(slots=True)
class SourceProvenance:
    """Provenance tuple carried by every machine-readable output."""

    regulation_id: str = ""
    designation: str = ""
    title: str = ""
    issue: str = UNKNOWN
    amendment: str = UNKNOWN
    version_slug: str = ""
    sha256: str = ""
    retrieved_at: str = ""
    download_url: str = ""
    landing_page: str = ""
    source_path: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "regulation_id": self.regulation_id,
            "designation": self.designation,
            "title": self.title,
            "issue": self.issue,
            "amendment": self.amendment,
            "version_slug": self.version_slug,
            "sha256": self.sha256,
            "retrieved_at": self.retrieved_at,
            "download_url": self.download_url,
            "landing_page": self.landing_page,
            "source_path": self.source_path,
        }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _version_fields(label: str, *candidates: str) -> tuple[str, str]:
    """Derive (issue, amendment) from the version label and any other hints.

    *label* is the publisher's own name for the edition. When it does not spell
    out an amendment number — ``eCFR as of 2025-01-01`` never will — the label
    itself is the amendment: it identifies the edition exactly, which is what
    the field is for.
    """
    issue = ""
    amendment = ""
    for text in (label, *candidates):
        if not text:
            continue
        if not amendment:
            match = _AMENDMENT_RE.search(text)
            if match:
                amendment = f"Amendment {match.group(1)}"
        if not issue:
            match = _ISSUE_RE.search(text)
            if match:
                issue = f"Issue {match.group(1)}"
        if _INITIAL_RE.search(text):
            issue = issue or "Initial issue"
            amendment = amendment or "Initial issue"
    return issue, amendment or label.strip()


def _designation_for(regulation_id: str, doc_title: str) -> str:
    """Short document designation, e.g. ``CS-VLA``."""
    if regulation_id:
        return regulation_id.upper()
    match = re.search(r"\(([A-Z][A-Z0-9-]{1,15})\)", doc_title or "")
    return match.group(1) if match else ""


def build_provenance(
    source_path: Path | str,
    *,
    document_key: str = "",
    document: Any = None,
) -> SourceProvenance:
    """Assemble provenance for a parsed source file.

    ``meta.yaml`` written by ``fetch`` sits next to the cached ``source.xml``.
    For an ad-hoc local file there is no such sidecar, so integrity is computed
    from the bytes on disk and the version fields fall back to whatever the
    document itself states.
    """
    source_path = Path(source_path)
    prov = SourceProvenance(source_path=str(source_path))

    meta: dict[str, Any] = {}
    meta_path = source_path.parent / "meta.yaml"
    if meta_path.is_file():
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            meta = {}
            prov.warnings.append("provenance_metadata_unreadable")
    else:
        prov.warnings.append("provenance_metadata_missing")

    version_meta = meta.get("version") or {}
    source_meta = meta.get("source") or {}
    integrity = meta.get("integrity") or {}

    prov.regulation_id = meta.get("document") or document_key or source_path.stem
    prov.title = meta.get("title") or getattr(document, "title", "") or ""
    prov.retrieved_at = meta.get("retrieved_at") or ""
    prov.version_slug = str(version_meta.get("slug") or "")
    prov.download_url = source_meta.get("download_url") or ""
    prov.landing_page = source_meta.get("landing_page") or ""
    prov.sha256 = integrity.get("sha256") or sha256_file(source_path)

    easa_meta: dict[str, Any] = {}
    if document is not None and getattr(document, "metadata", None):
        easa_meta = document.metadata.get("easa") or {}
    amended_by = easa_meta.get("amended_by") or []
    if isinstance(amended_by, str):
        amended_by = [amended_by]

    issue, amendment = _version_fields(
        version_meta.get("label") or "",
        getattr(document, "version", "") or "",
        prov.title,
        *amended_by,
    )

    if not issue:
        prov.warnings.append("issue_not_determined")
    if not amendment:
        prov.warnings.append("amendment_not_determined")

    prov.issue = issue or UNKNOWN
    prov.amendment = amendment or UNKNOWN
    prov.designation = _designation_for(prov.regulation_id, prov.title)
    return prov
