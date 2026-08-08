"""Utility functions."""

import re
import unicodedata


def slugify(text: str, max_length: int = 100) -> str:
    """Convert text to URL-friendly slug."""
    # Normalize unicode
    text = unicodedata.normalize("NFKD", text)

    # Remove non-ASCII
    text = text.encode("ascii", "ignore").decode("ascii")

    # Replace spaces and special chars with hyphens
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")

    # Lowercase
    text = text.lower()

    # Truncate
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")

    return text


def slugify_rule(designation: str) -> str:
    """Create slug for rule designation (e.g., CS-VLA.303 -> cs-vla-303)."""
    # Replace dots and spaces with hyphens
    slug = designation.replace(".", "-").replace(" ", "-")
    return slug.lower()


def extract_designation(text: str) -> str:
    """Extract rule designation from text."""
    import re
    patterns = [
        r"(CS[-\s]?[A-Z0-9]+(?:\.\d+)?)",
        r"(AMC\d*\s+CS[-\s]?[A-Z0-9]+(?:\.\d+)?)",
        r"(GM\d*\s+CS[-\s]?[A-Z0-9]+(?:\.\d+)?)",
        r"(\d+\.\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).replace(" ", "-")
    return ""