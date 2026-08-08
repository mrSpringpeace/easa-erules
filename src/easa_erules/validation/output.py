"""Validate a conversion output directory on disk."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from .assets import check_output_assets
from .report import ValidationReport


def validate_conversion(output_dir: Path) -> ValidationReport:
    """Validate a conversion output directory for completeness and integrity."""
    report = ValidationReport()
    output_dir = Path(output_dir)

    if not output_dir.is_dir():
        report.errors.append({
            "type": "not_a_directory",
            "path": str(output_dir),
            "message": f"Output path is not a directory: {output_dir}",
        })
        return report.finalize()

    # --- Sidecars ---
    conversion_report = output_dir / "conversion-report.json"
    if conversion_report.exists():
        try:
            prior = json.loads(conversion_report.read_text(encoding="utf-8"))
            # Prefer richer counts from the parse-time report when present
            for key in (
                "topics",
                "paragraphs",
                "tables",
                "images",
                "requirements",
                "sections",
                "unique_erules_ids",
            ):
                if key in prior and isinstance(prior[key], int):
                    setattr(report, key, prior[key])
            if prior.get("warnings"):
                report.warnings.append({
                    "type": "prior_report_warnings",
                    "count": len(prior["warnings"]),
                    "message": f"conversion-report.json lists {len(prior['warnings'])} warning(s)",
                })
            if prior.get("errors"):
                report.warnings.append({
                    "type": "prior_report_errors",
                    "count": len(prior["errors"]),
                    "message": f"conversion-report.json lists {len(prior['errors'])} error(s)",
                })
        except (json.JSONDecodeError, OSError) as exc:
            report.warnings.append({
                "type": "invalid_conversion_report",
                "message": f"Could not read conversion-report.json: {exc}",
            })
    else:
        report.warnings.append({
            "type": "missing_conversion_report",
            "message": "conversion-report.json not found",
        })

    document_json = output_dir / "document.json"
    if document_json.exists():
        try:
            data = json.loads(document_json.read_text(encoding="utf-8"))
            if "document" not in data and "type" not in data:
                report.warnings.append({
                    "type": "unexpected_document_json",
                    "message": "document.json missing expected document root",
                })
        except (json.JSONDecodeError, OSError) as exc:
            report.errors.append({
                "type": "invalid_document_json",
                "message": f"Could not parse document.json: {exc}",
            })

    metadata_yaml = output_dir / "metadata.yaml"
    if metadata_yaml.exists():
        try:
            meta = yaml.safe_load(metadata_yaml.read_text(encoding="utf-8")) or {}
            if not meta.get("document_id") and not meta.get("title"):
                report.warnings.append({
                    "type": "sparse_metadata",
                    "message": "metadata.yaml has no document_id or title",
                })
        except yaml.YAMLError as exc:
            report.warnings.append({
                "type": "invalid_metadata_yaml",
                "message": f"Could not parse metadata.yaml: {exc}",
            })

    # --- Rules / topics ---
    rules_dir = output_dir / "rules"
    rule_files = list(rules_dir.glob("*.md")) if rules_dir.is_dir() else []
    if rule_files:
        report.topics = max(report.topics, len(rule_files))

    md_files = list(output_dir.rglob("*.md"))
    if not md_files:
        report.errors.append({
            "type": "no_markdown",
            "message": "No Markdown files found in output directory",
        })

    # --- Per-file markdown checks ---
    paragraphs = 0
    tables = 0
    for md_file in md_files:
        p, t, warns = _inspect_markdown_file(md_file, output_dir)
        paragraphs += p
        tables += t
        report.warnings.extend(warns)

    # Only override if we didn't load richer counts from conversion-report
    if report.paragraphs == 0:
        report.paragraphs = paragraphs
    if report.tables == 0:
        report.tables = tables

    # --- Assets / image links ---
    check_output_assets(output_dir, report)

    # --- Internal markdown links to rules ---
    _check_rule_links(output_dir, report)

    return report.finalize()


def _inspect_markdown_file(
    filepath: Path,
    output_dir: Path,
) -> tuple[int, int, list[dict[str, Any]]]:
    """Return (paragraph_count, table_count, warnings) for one markdown file."""
    warnings: list[dict[str, Any]] = []
    content = filepath.read_text(encoding="utf-8")
    rel = str(filepath.relative_to(output_dir))

    frontmatter: dict[str, Any] = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                warnings.append({
                    "type": "invalid_frontmatter",
                    "file": rel,
                    "message": f"Invalid YAML frontmatter in {rel}",
                })
            body = parts[2]

    if filepath.name != "index.md" and content.startswith("---"):
        if not frontmatter.get("id") and not frontmatter.get("rule"):
            warnings.append({
                "type": "missing_id",
                "file": rel,
                "message": f"Frontmatter missing id/rule in {rel}",
            })

    paragraphs = 0
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "-", "*", "|", ">", "!", "<", "```")):
            continue
        if stripped.startswith("[") and "](" in stripped:
            continue
        paragraphs += 1

    # Count markdown tables by header separator rows
    tables = len(re.findall(r"^\|[\s\-:|]+\|$", body, flags=re.MULTILINE))

    return paragraphs, tables, warnings


def _check_rule_links(output_dir: Path, report: ValidationReport) -> None:
    """Flag broken relative markdown links to local files."""
    import re

    for md_file in output_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        rel_file = str(md_file.relative_to(output_dir))
        for match in re.finditer(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", content):
            target = match.group(1).strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            # strip optional title
            path_part = target.split()[0].strip("\"'")
            if path_part.startswith("#"):
                continue
            resolved = (md_file.parent / path_part).resolve()
            if not resolved.exists():
                report.warnings.append({
                    "type": "broken_link",
                    "file": rel_file,
                    "path": path_part,
                    "message": f"Broken relative link in {rel_file}: {path_part}",
                })
