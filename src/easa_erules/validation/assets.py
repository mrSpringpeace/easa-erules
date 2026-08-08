"""Asset integrity validation (parse-time and on-disk)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..model import FigureNode
from ..model.assets import AssetCollection
from .report import ValidationReport


def check_figure_assets(
    doc: Any,
    report: ValidationReport,
    assets: AssetCollection | None = None,
) -> None:
    """Ensure every FigureNode has a corresponding asset with binary data."""
    asset_names = set(assets.assets.keys()) if assets else set()

    def walk(node: Any) -> None:
        if isinstance(node, FigureNode):
            name = node.image_path
            if not name:
                report.missing_images.append("<empty>")
                report.errors.append({
                    "type": "missing_image",
                    "message": "Figure node has empty image_path",
                    "node_id": getattr(node, "id", ""),
                })
            elif assets is not None and name not in asset_names:
                report.missing_images.append(name)
                report.errors.append({
                    "type": "missing_image",
                    "path": name,
                    "message": f"Figure references asset not in collection: {name}",
                    "node_id": getattr(node, "id", ""),
                })
            elif assets is not None:
                asset = assets.assets.get(name)
                if asset is not None and not asset.data:
                    report.missing_images.append(name)
                    report.errors.append({
                        "type": "empty_image_data",
                        "path": name,
                        "message": f"Asset has empty binary data: {name}",
                    })

        if isinstance(node, type(doc)) or hasattr(node, "children"):
            # Table cells
            from ..model import TableNode

            if isinstance(node, TableNode):
                for row in node.headers + node.rows:
                    for cell in row:
                        items = cell if isinstance(cell, list) else [cell]
                        for item in items:
                            walk(item)

        for child in getattr(node, "children", []) or []:
            walk(child)

    walk(doc)


def check_output_assets(
    output_dir: Path,
    report: ValidationReport,
    assets_dir_name: str = "assets",
) -> None:
    """Validate markdown image references resolve to files under output_dir."""
    import re

    assets_dir = output_dir / assets_dir_name
    if assets_dir.is_dir():
        report.images = len([p for p in assets_dir.iterdir() if p.is_file()])

    for md_file in sorted(output_dir.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        rel_file = str(md_file.relative_to(output_dir))
        for match in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", content):
            rel = match.group(1).strip()
            if rel.startswith(("http://", "https://", "data:")):
                continue
            target = (md_file.parent / rel).resolve()
            try:
                target.relative_to(output_dir.resolve())
            except ValueError:
                # Path escapes output dir — still check existence
                pass
            if not target.exists():
                report.missing_images.append(rel)
                report.errors.append({
                    "type": "missing_image",
                    "file": rel_file,
                    "path": rel,
                    "message": f"Image not found on disk: {rel} (from {rel_file})",
                })
