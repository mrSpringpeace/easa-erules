"""Validation module."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass
class ValidationReport:
    """Report from validation."""
    topics: int = 0
    paragraphs: int = 0
    tables: int = 0
    images: int = 0
    warnings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topics": self.topics,
            "paragraphs": self.paragraphs,
            "tables": self.tables,
            "images": self.images,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def validate_conversion(output_dir: Path) -> ValidationReport:
    """Validate a conversion output directory."""
    report = ValidationReport()

    # Find index.md or main markdown file
    index_file = output_dir / "index.md"
    if not index_file.exists():
        # Try single file
        md_files = list(output_dir.glob("*.md"))
        if md_files:
            index_file = md_files[0]

    if index_file.exists():
        _validate_markdown_file(index_file, report)

    # Check assets
    assets_dir = output_dir / "assets"
    if assets_dir.exists():
        report.images = len(list(assets_dir.glob("*")))

    # Check rules directory
    rules_dir = output_dir / "rules"
    if rules_dir.exists():
        report.topics = len(list(rules_dir.glob("*.md")))

    return report


def _validate_markdown_file(filepath: Path, report: ValidationReport) -> None:
    """Validate a single markdown file."""
    content = filepath.read_text(encoding="utf-8")

    # Count elements
    lines = content.split("\n")
    in_frontmatter = False
    frontmatter_lines = []
    body_lines = []

    for line in lines:
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
            else:
                in_frontmatter = False
            continue

        if in_frontmatter:
            frontmatter_lines.append(line)
        else:
            body_lines.append(line)

    body = "\n".join(body_lines)

    # Count paragraphs (non-empty lines not starting with #, -, *, |, >)
    paragraphs = 0
    for line in body_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "-", "*", "|", ">", "!", "[", "**", "<")):
            paragraphs += 1

    report.paragraphs = paragraphs

    # Count tables
    report.tables = body.count("|") // 2  # rough estimate

    # Count figures
    report.images = body.count("!(")

    # Check for unresolved references
    if "[[]" in body or "]( #" in body:
        report.warnings.append({
            "type": "unresolved_reference",
            "file": str(filepath),
        })

    # Check frontmatter
    if frontmatter_lines:
        try:
            fm = yaml.safe_load("\n".join(frontmatter_lines))
            if not fm.get("id"):
                report.warnings.append({
                    "type": "missing_id",
                    "file": str(filepath),
                })
        except yaml.YAMLError:
            report.warnings.append({
                "type": "invalid_frontmatter",
                "file": str(filepath),
            })