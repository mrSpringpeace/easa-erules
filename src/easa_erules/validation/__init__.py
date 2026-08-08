"""Validation module."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ValidationReport:
    """Report from validation."""
    topics: int = 0
    paragraphs: int = 0
    tables: int = 0
    images: int = 0
    requirements: int = 0
    sections: int = 0
    unique_erules_ids: int = 0
    duplicate_erules_ids: list[str] = field(default_factory=list)
    unresolved_references: list[dict[str, Any]] = field(default_factory=list)
    missing_images: list[str] = field(default_factory=list)
    unknown_elements: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topics": self.topics,
            "paragraphs": self.paragraphs,
            "tables": self.tables,
            "images": self.images,
            "requirements": self.requirements,
            "sections": self.sections,
            "unique_erules_ids": self.unique_erules_ids,
            "duplicate_erules_ids": self.duplicate_erules_ids,
            "unresolved_references": self.unresolved_references,
            "missing_images": self.missing_images,
            "unknown_elements": self.unknown_elements,
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


# Parse-time validation
def validate_document(doc, assets=None, references=None, parse_warnings=None, unknown_elements=None) -> ValidationReport:
    """Validate a parsed document for integrity."""
    report = ValidationReport()
    
    seen_erules_ids = set()
    duplicate_ids = set()
    
    def check_node(node):
        # Count nodes
        from easa_erules.model import (
            RegulationDocument, RegulationSection, RegulationRequirement,
            ParagraphNode, HeadingNode, TableNode, FigureNode,
            ReferenceNode, InternalReferenceNode
        )
        
        if isinstance(node, RegulationRequirement):
            report.requirements += 1
        elif isinstance(node, RegulationSection):
            report.sections += 1
        elif isinstance(node, ParagraphNode):
            report.paragraphs += 1
        elif isinstance(node, HeadingNode):
            pass  # counted as part of parent
        elif isinstance(node, TableNode):
            report.tables += 1
        elif isinstance(node, FigureNode):
            report.images += 1
        
        # Check ERulesId uniqueness
        if hasattr(node, 'erules_id') and node.erules_id:
            if node.erules_id in seen_erules_ids:
                duplicate_ids.add(node.erules_id)
            else:
                seen_erules_ids.add(node.erules_id)
        
        # Check unresolved internal references
        if isinstance(node, InternalReferenceNode):
            if not node.target_id:
                report.unresolved_references.append({
                    "source_id": getattr(node, 'id', ''),
                    "target_designation": node.target_designation,
                    "text": node.text,
                })
        
        # Recurse
        for child in getattr(node, 'children', []):
            check_node(child)
    
    check_node(doc)
    
    report.unique_erules_ids = len(seen_erules_ids)
    report.duplicate_erules_ids = list(duplicate_ids)
    
    # Add warnings for duplicates
    for dup_id in duplicate_ids:
        report.warnings.append({
            "type": "duplicate_erules_id",
            "erules_id": dup_id,
        })
    
    # Check references
    if references:
        for ref in references.by_designation.values():
            if not ref.resolved:
                report.unresolved_references.append({
                    "source_id": ref.source_id,
                    "target_designation": ref.target_designation,
                    "raw_text": ref.raw_text,
                })
    
    # Include parse warnings
    if parse_warnings:
        report.warnings.extend(parse_warnings)
    
    # Include unknown elements
    if unknown_elements:
        report.unknown_elements.extend(unknown_elements)
    
    return report