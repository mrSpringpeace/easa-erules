"""Detect cross-references written as plain text.

Official EAR packages do not mark cross-references up as elements — a rule that
points at another rule simply spells it out in running text ("...as required by
CS-VLA 303..."). Without this pass the reference graph is empty on every real
document, which is worse than useless for an agent: an empty ``refs`` result
looks like a confident "this rule references nothing".

The pass rewrites matching runs of text into ``InternalReferenceNode`` children
so ``refs``, the validation report and the search index all see them. Nodes
created here carry ``metadata["detected"] = True`` so renderers can tell them
apart from references that were explicit in the source.
"""

from __future__ import annotations

import re
from typing import Any

from ..model import (
    AcceptableMeansOfComplianceNode,
    GuidanceNode,
    HeadingNode,
    InternalReferenceNode,
    RegulationRequirement,
    RegulationSection,
    TableNode,
    TextNode,
)
from ..util.slugify import normalize_designation

_TOPIC_TYPES = (
    RegulationRequirement,
    GuidanceNode,
    AcceptableMeansOfComplianceNode,
    RegulationSection,
)

# Ordered most specific first; case-sensitive on purpose — regulatory text
# writes designations in upper case, and matching "cs" loosely produces noise.
_SUB = r"(?:\([a-z0-9]+\))*"
_REF_RE = re.compile(
    r"(?<![\w./-])"
    r"(?:"
    rf"(?:AMC|GM)\d*\s+CS[-\s]?[A-Z]{{2,12}}[.\s]\d+{_SUB}"
    rf"|(?:AMC|GM)\d*\s+CS[-\s]?\d+\.\d+{_SUB}"
    rf"|(?:AMC|GM)\d*\s+[A-Z]{{2,12}}\s+\d+{_SUB}"
    rf"|CS[-\s][A-Z]{{2,12}}[.\s]\d+{_SUB}"
    rf"|CS[-\s]\d+\.\d+{_SUB}"
    r")"
)


def find_designations(text: str) -> list[tuple[int, int, str]]:
    """Return ``(start, end, canonical_designation)`` for every match in *text*."""
    hits: list[tuple[int, int, str]] = []
    for match in _REF_RE.finditer(text):
        raw = match.group(0)
        canonical = normalize_designation(raw)
        if canonical:
            hits.append((match.start(), match.end(), canonical))
    return hits


def detect_text_references(root: Any) -> int:
    """Rewrite plain-text designations into reference nodes. Returns match count."""
    found = 0

    def split_run(text: str, own: str, out: list[Any]) -> bool:
        """Append text/reference nodes for *text* to *out*. True if any ref found."""
        nonlocal found
        hits = [h for h in find_designations(text) if h[2] != own]
        if not hits:
            if text:
                out.append(TextNode(text=text))
            return False

        cursor = 0
        for start, end, designation in hits:
            if start > cursor:
                out.append(TextNode(text=text[cursor:start]))
            ref = InternalReferenceNode(
                text=text[start:end],
                target_designation=designation,
            )
            ref.metadata["detected"] = True
            out.append(ref)
            found += 1
            cursor = end
        if cursor < len(text):
            out.append(TextNode(text=text[cursor:]))
        return True

    def split_inline(container: Any, own: str) -> None:
        children = getattr(container, "children", None)
        if not children:
            return

        rebuilt: list[Any] = []
        changed = False
        # Word splits a single designation across several runs ("CS-VLA " + "303"),
        # so consecutive plain-text children are joined before matching. They carry
        # no formatting of their own, which makes the merge lossless.
        buffer: list[str] = []

        def flush() -> None:
            nonlocal changed
            if not buffer:
                return
            if split_run("".join(buffer), own, rebuilt):
                changed = True
            buffer.clear()

        for child in children:
            if isinstance(child, TextNode):
                buffer.append(child.text or "")
                continue
            flush()
            # Nested inline containers (bold, italic, …) are reached by walk()
            rebuilt.append(child)
        flush()

        if changed:
            for node in rebuilt:
                node.parent = container
            container.children = rebuilt

    def walk(node: Any, own: str) -> None:
        if isinstance(node, _TOPIC_TYPES):
            # Undesignated nested sections must not wipe the enclosing rule's
            # designation, or the rule starts "referencing" itself.
            own = normalize_designation(getattr(node, "designation", "") or "") or own

        # Headings are the rule's own label, not a reference to anything.
        # References already marked up in the source stay as they are.
        if isinstance(node, (HeadingNode, InternalReferenceNode)):
            return

        if isinstance(node, TableNode):
            for row in node.headers + node.rows:
                for cell in row:
                    items = cell if isinstance(cell, list) else [cell]
                    for item in items:
                        walk(item, own)

        split_inline(node, own)

        for child in list(getattr(node, "children", []) or []):
            walk(child, own)

    walk(root, "")
    return found
