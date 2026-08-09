"""Utility functions for slugs and regulatory designations."""

from __future__ import annotations

import re
import unicodedata


def slugify(text: str, max_length: int = 100) -> str:
    """Convert text to URL-friendly slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-").lower()
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text


def slugify_rule(designation: str) -> str:
    """Create slug for rule designation (e.g., CS-VLA.303 -> cs-vla-303)."""
    slug = designation.replace(".", "-").replace(" ", "-")
    return slug.lower()


def _clean_designation_text(text: str) -> str:
    """Normalize whitespace / non-breaking spaces for designation matching."""
    if not text:
        return ""
    text = text.replace("\xa0", " ").replace("\u00a0", " ")
    text = re.sub(r"\s+", " ", text.strip())
    return text


def normalize_designation(text: str) -> str:
    """Canonical spacing/hyphen form for designations and cross-refs.

    Examples:
      - ``CS 23.2000`` → ``CS-23.2000``
      - ``CS-VLA 1`` → ``CS-VLA.1``
      - ``AMC1  23.2100`` → ``AMC1 CS-23.2100``
      - ``AMC VLA 21(c)`` → ``AMC VLA 21(c)``
    """
    text = _clean_designation_text(text)
    if not text:
        return ""

    # CS 23.xxx / CS-23.xxx → CS-23.xxx
    text = re.sub(r"\bCS\s+(\d)", r"CS-\1", text, flags=re.IGNORECASE)

    # CS-VLA 1 / CS VLA 1 → CS-VLA.1  (letter code + bare number; keep (c) suffix)
    text = re.sub(
        r"\b(CS)[-\s]?([A-Z]{2,12})\s+(\d+(?:\([a-z0-9]+\))?)",
        lambda m: f"CS-{m.group(2).upper()}.{m.group(3)}",
        text,
        flags=re.IGNORECASE,
    )

    # Ensure CS- prefix casing
    text = re.sub(r"\bcs-", "CS-", text, flags=re.IGNORECASE)

    # AMC1 23.xxx / AMC1 CS-23.xxx → AMC1 CS-23.xxx
    text = re.sub(
        r"\b((?:AMC|GM)\d*)\s+(?:CS-)?(\d+\.\d+(?:\([a-z0-9]+\))?)",
        lambda m: f"{m.group(1).upper()} CS-{m.group(2)}",
        text,
        flags=re.IGNORECASE,
    )

    # AMC VLA 1 / AMC1 VLA 21(c) — keep letter-code form, normalize spaces
    text = re.sub(
        r"\b((?:AMC|GM)\d*)\s+([A-Z]{2,12})\s+(\d+(?:\([a-z0-9]+\))?)",
        lambda m: f"{m.group(1).upper()} {m.group(2).upper()} {m.group(3)}",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(r"-{2,}", "-", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# End-of-token: avoid bare ``\b`` after ``)`` (``)`` is non-word, so ``(c) ``
# would fail a trailing ``\b`` and drop the parenthetical).
_TOK_END = r"(?=\s|$|[^\w.(])"

# Patterns ordered from most specific to least. Applied only near the start of
# the candidate string so preamble/TOC blobs do not produce false positives.
_DESIGNATION_PATTERNS: list[re.Pattern[str]] = [
    # AMC VLA 21(c) / AMC VLA 1 / GM LSA 3
    re.compile(
        rf"^((?:AMC|GM)\d*)\s+([A-Z]{{2,12}})\s+(\d+(?:\([a-z0-9]+\))?){_TOK_END}",
        re.IGNORECASE,
    ),
    # AMC1 CS-23.2000 / AMC1 23.2000 / GM2 CS 23.2010
    re.compile(
        rf"^((?:AMC|GM)\d*)\s+(?:CS[-\s]?)?(\d+\.\d+(?:\([a-z0-9]+\))?){_TOK_END}",
        re.IGNORECASE,
    ),
    # AMC1 CS-VLA.303 / AMC CS-TEST.300
    re.compile(
        rf"^((?:AMC|GM)\d*)\s+(CS[-\s]?[A-Z]{{2,12}}(?:[.\s]\d+(?:\([a-z0-9]+\))?)?){_TOK_END}",
        re.IGNORECASE,
    ),
    # CS-VLA 1 / CS-VLA.303 / CS VLA 21(c)
    re.compile(
        rf"^(CS)[-\s]?([A-Z]{{2,12}})(?:[.\s]+(\d+(?:\([a-z0-9]+\))?))?{_TOK_END}",
        re.IGNORECASE,
    ),
    # CS 23.2000 / CS-23.2000
    re.compile(
        rf"^(CS)[-\s]?(\d+\.\d+(?:\([a-z0-9]+\))?){_TOK_END}",
        re.IGNORECASE,
    ),
]

def extract_designation(text: str, *, require_number: bool = False) -> str:
    """Extract a rule designation from the start of title/first-line text.

    Parameters
    ----------
    text:
        Title or first paragraph line (not a full topic body blob).
    require_number:
        If True, reject bare document codes such as ``CS-VLA`` / ``CS-23``
        without a paragraph number (reduces duplicate-id noise on preambles).
    """
    text = _clean_designation_text(text)
    if not text:
        return ""

    # Only consider the leading portion of a title line
    head = text[:120]

    for pattern in _DESIGNATION_PATTERNS:
        match = pattern.match(head)
        if not match:
            continue
        groups = match.groups()
        raw = match.group(0)

        # CS letter-code without number (group 3 empty on pattern 4)
        if (
            require_number
            and len(groups) >= 3
            and groups[0]
            and groups[0].upper() == "CS"
            and groups[1]
            and groups[1].isalpha()
            and not groups[2]
        ):
            continue

        # Bare CS-23 / CS-VLA without paragraph number when require_number
        if require_number and re.fullmatch(
            r"CS[-\s]?[A-Z0-9]+", raw.strip(), flags=re.IGNORECASE
        ):
            continue

        return normalize_designation(raw)

    return ""


def extract_designation_from_lines(lines: list[str]) -> str:
    """Try successive non-empty lines until a full designation is found."""
    for line in lines:
        des = extract_designation(line, require_number=True)
        if des:
            return des
        # Allow bare codes only if the whole line is essentially just the code
        des = extract_designation(line, require_number=False)
        if des and len(line.strip()) <= len(des) + 2:
            return des
    return ""


def extract_ed_decision(text: str) -> str:
    """Extract an ED Decision identifier from a line if present."""
    text = _clean_designation_text(text)
    match = re.search(
        r"\bED\s+Decision\s+\d{4}/\d+[A-Z]*(?:/[A-Z]+)?\b",
        text,
        re.IGNORECASE,
    )
    if match:
        return re.sub(r"\s+", " ", match.group(0)).strip()
    return ""
