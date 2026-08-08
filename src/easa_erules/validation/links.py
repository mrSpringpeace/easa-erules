"""Reference / link validation."""

from __future__ import annotations

from typing import Any

from ..model import InternalReferenceNode
from ..model.references import ReferenceIndex
from .report import ValidationReport


def check_internal_references(
    doc: Any,
    report: ValidationReport,
    references: ReferenceIndex | None = None,
) -> None:
    """Flag unresolved internal references in the AST and reference index."""
    seen: set[tuple[str, str]] = set()

    def walk(node: Any) -> None:
        if isinstance(node, InternalReferenceNode):
            if not node.target_id:
                key = (node.target_designation or "", node.text or "")
                if key not in seen:
                    seen.add(key)
                    entry = {
                        "source_id": getattr(node, "id", "") or "",
                        "target_designation": node.target_designation,
                        "text": node.text,
                        "status": "unresolved",
                    }
                    report.unresolved_references.append(entry)
                    report.warnings.append({
                        "type": "unresolved_reference",
                        **entry,
                    })
        for child in getattr(node, "children", []) or []:
            walk(child)

    walk(doc)

    if references is not None:
        for ref in references.by_designation.values():
            if ref.resolved:
                continue
            key = (ref.target_designation or "", ref.raw_text or "")
            if key in seen:
                continue
            seen.add(key)
            entry = {
                "source_id": ref.source_id,
                "target_designation": ref.target_designation,
                "raw_text": ref.raw_text,
                "status": "unresolved",
            }
            report.unresolved_references.append(entry)
            report.warnings.append({
                "type": "unresolved_reference",
                **entry,
            })
