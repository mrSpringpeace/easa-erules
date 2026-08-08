"""CLI for easa-erules."""

import json
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from . import __version__
from .input.package import OpcPackage
from .model import (
    AcceptableMeansOfComplianceNode,
    FigureNode,
    GuidanceNode,
    HeadingNode,
    ListNode,
    ParagraphNode,
    RegulationDocument,
    RegulationRequirement,
    RegulationSection,
    TableNode,
)
from .parser import EasaDocumentParser, parse_easa_document
from .render import render_json, render_markdown
from .validation import build_conversion_report, validate_document

app = typer.Typer(
    name="easa-erules",
    help="Universal toolkit for EASA Easy Access Rules XML publications",
    add_completion=False,
)

console = Console()


def _load_package(source: str) -> tuple[OpcPackage, str]:
    """Load an OOXML/Flat OPC package from a local path.

    Returns (package, stem_id). Document IDs from the registry are not
    downloadable yet (fetch lands in a later milestone); only local paths work.
    """
    path = Path(source)
    if path.exists():
        return OpcPackage.from_file(path), path.stem

    # Friendly message if the user passed a registry id (fetch not implemented)
    try:
        from .sources.registry import get_source

        info = get_source(source)
        console.print(
            f"[red]Source '{info['id']}' is registered but not available locally.[/red]"
        )
        console.print(
            "Pass a path to a local XML/DOCX file. "
            "`easa-erules fetch` will be available in a later release."
        )
    except KeyError:
        console.print(f"[red]File not found: {source}[/red]")
    raise typer.Exit(1)


@app.command("list")
def list_sources():
    """List available built-in regulation sources."""
    from .sources.registry import REGISTRY

    table = Table(title="EASA Regulation Sources")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Aliases", style="dim")

    for key, source in REGISTRY.items():
        table.add_row(
            key,
            source["title"],
            source["type"],
            ", ".join(source.get("aliases", [])),
        )

    console.print(table)


@app.command()
def info(doc_id: str):
    """Show information about a regulation source (ID or alias)."""
    from .sources.registry import get_source

    try:
        source = get_source(doc_id)
    except KeyError:
        console.print(f"[red]Unknown document: {doc_id}[/red]")
        console.print("Use 'easa-erules list' to see available documents.")
        raise typer.Exit(1)

    console.print(f"[bold cyan]{source['title']}[/bold cyan]")
    console.print(f"  ID: {source['id']}")
    console.print(f"  Type: {source['type']}")
    console.print(f"  Authority: {source['authority']}")
    console.print(f"  Landing page: {source['landing_page']}")
    console.print(f"  Preferred format: {source['preferred_format']}")
    if source.get("aliases"):
        console.print(f"  Aliases: {', '.join(source['aliases'])}")


@app.command()
def inspect(
    source: str = typer.Argument(..., help="Path to XML/DOCX file"),
):
    """Inspect an EASA XML document structure."""
    package, _ = _load_package(source)

    parser = EasaDocumentParser(package)
    try:
        result = parser.parse()
    except Exception as e:
        console.print(f"[red]Parse error: {e}[/red]")
        raise typer.Exit(1)

    doc = result.document
    stats = _collect_stats(doc)

    console.print(f"[bold]Document:[/bold] {doc.title}")
    console.print(f"[bold]ID:[/bold] {doc.document_id}")
    console.print(f"[bold]Authority:[/bold] {doc.authority}")
    console.print(f"[bold]Version:[/bold] {doc.version}")

    table = Table(title="Structure Statistics")
    table.add_column("Element", style="cyan")
    table.add_column("Count", style="green", justify="right")

    for key, value in stats.items():
        table.add_row(key, str(value))

    console.print(table)

    if doc.metadata.get("easa"):
        console.print("\n[bold]EASA Metadata:[/bold]")
        console.print(JSON.from_data(doc.metadata["easa"]))

    if result.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for w in result.warnings:
            console.print(f"  - {w}")

    if result.unknown_elements:
        console.print("\n[bold red]Unknown Elements:[/bold red]")
        for u in result.unknown_elements:
            console.print(f"  - {u}")


def _collect_stats(doc: RegulationDocument) -> dict:
    """Collect statistics about document structure."""
    stats = {
        "Topics/Sections": 0,
        "Requirements": 0,
        "Guidance": 0,
        "AMC": 0,
        "Paragraphs": 0,
        "Headings": 0,
        "Tables": 0,
        "Figures": 0,
        "Lists": 0,
    }

    def count(node: Any) -> None:
        if isinstance(node, RegulationSection):
            stats["Topics/Sections"] += 1
        elif isinstance(node, RegulationRequirement):
            stats["Requirements"] += 1
        elif isinstance(node, GuidanceNode):
            stats["Guidance"] += 1
        elif isinstance(node, AcceptableMeansOfComplianceNode):
            stats["AMC"] += 1
        elif isinstance(node, ParagraphNode):
            stats["Paragraphs"] += 1
        elif isinstance(node, HeadingNode):
            stats["Headings"] += 1
        elif isinstance(node, TableNode):
            stats["Tables"] += 1
        elif isinstance(node, FigureNode):
            stats["Figures"] += 1
        elif isinstance(node, ListNode):
            stats["Lists"] += 1

        for child in getattr(node, "children", []):
            count(child)

    count(doc)
    return stats


def _write_assets(output: Path, assets: Any, asset_dir_name: str = "assets") -> int:
    """Write extracted binary assets to disk. Returns count written."""
    if not assets or not getattr(assets, "assets", None):
        return 0

    assets_dir = output / asset_dir_name
    assets_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for name, asset in assets.assets.items():
        path = assets_dir / name
        path.write_bytes(asset.data)
        count += 1
    return count


def _write_metadata_yaml(output: Path, doc: RegulationDocument) -> None:
    """Write metadata.yaml sidecar for split/single conversions."""
    meta = {
        "document_id": doc.document_id,
        "title": doc.title,
        "authority": doc.authority or "EASA",
        "version": doc.version,
        "parser_version": __version__,
        "easa": doc.metadata.get("easa") or doc.easa_metadata,
    }
    (output / "metadata.yaml").write_text(
        yaml.dump(meta, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


@app.command()
def convert(
    source: str = typer.Argument(..., help="Path to XML/DOCX file"),
    output: Path | None = typer.Option(None, "-o", "--output", help="Output directory"),
    split: bool = typer.Option(False, "--split", help="Split output by rule/topic"),
    format: str = typer.Option(
        "markdown", "--format", "-f", help="Output format: markdown, json"
    ),
    asset_prefix: str = typer.Option("assets", "--assets", help="Asset path prefix"),
):
    """Convert EASA XML to Markdown or JSON."""
    package, doc_id = _load_package(source)

    parser = EasaDocumentParser(package)
    with console.status("Parsing document..."):
        result = parser.parse()

    doc = result.document

    with console.status("Validating document..."):
        validation_report = validate_document(
            doc,
            result.assets,
            result.references,
            parse_warnings=result.warnings,
            unknown_elements=result.unknown_elements,
            source_topic_count=result.source_topic_count,
        )

    with console.status("Rendering output..."):
        if format == "markdown":
            files = render_markdown(doc, split_by_rule=split, asset_prefix=asset_prefix)
        elif format == "json":
            result_json = render_json(doc, result.assets, result.references)
            files = {
                f"{doc.document_id or doc_id}.json": json.dumps(
                    result_json, indent=2, ensure_ascii=False
                )
            }
        else:
            console.print(f"[red]Unknown format: {format}[/red]")
            raise typer.Exit(1)

    if output:
        output.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            filepath = output / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")

        # Always emit full JSON AST alongside markdown when converting to MD
        if format == "markdown":
            doc_json = render_json(doc, result.assets, result.references)
            (output / "document.json").write_text(
                json.dumps(doc_json, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            _write_metadata_yaml(output, doc)

        written = _write_assets(output, result.assets, asset_prefix)

        # Re-build report including on-disk asset checks
        validation_report = build_conversion_report(
            doc,
            assets=result.assets,
            references=result.references,
            parse_warnings=result.warnings,
            unknown_elements=result.unknown_elements,
            source_topic_count=result.source_topic_count,
            output_dir=output,
        )

        report_path = output / "conversion-report.json"
        report_path.write_text(
            json.dumps(validation_report.to_dict(), indent=2),
            encoding="utf-8",
        )

        console.print(f"[green]Output written to {output}[/green]")
        if written:
            console.print(f"[green]Assets written: {written} file(s) under {asset_prefix}/[/green]")
        console.print(f"[green]Conversion report written to {report_path}[/green]")
        if not validation_report.ok:
            console.print(
                f"[yellow]Validation reported issues "
                f"({len(validation_report.errors)} error(s), "
                f"{len(validation_report.warnings)} warning(s)). "
                f"See {report_path}[/yellow]"
            )
    else:
        if split and len(files) > 1:
            console.print(
                f"[yellow]Split output has {len(files)} files. Use --output to save.[/yellow]"
            )
            for fname in list(files)[:5]:
                console.print(f"  {fname}")
            if len(files) > 5:
                console.print(f"  ... and {len(files) - 5} more")
        else:
            for content in files.values():
                console.print(content)


@app.command()
def extract(
    source: str = typer.Argument(..., help="Path to XML/DOCX file"),
    rule: str = typer.Argument(..., help="Rule designation (e.g., CS-VLA.303)"),
    format: str = typer.Option(
        "json", "--format", "-f", help="Output format: json, markdown"
    ),
):
    """Extract a single rule by designation."""
    package, _ = _load_package(source)
    doc = parse_easa_document(package)

    target = _find_rule(doc, rule)
    if not target:
        console.print(f"[red]Rule not found: {rule}[/red]")
        raise typer.Exit(1)

    if format == "json":
        result = render_json(target)
        console.print(JSON.from_data(result))
    else:
        files = render_markdown(target)
        for content in files.values():
            console.print(content)


def _find_rule(node: Any, designation: str) -> Any | None:
    """Find a rule by designation (case-insensitive)."""
    needle = designation.replace(" ", "-").upper()

    def matches(n: Any) -> bool:
        for attr in ("designation", "erules_id"):
            val = getattr(n, attr, None)
            if val and val.replace(" ", "-").upper() == needle:
                return True
        return False

    if matches(node):
        return node

    for child in getattr(node, "children", []):
        found = _find_rule(child, designation)
        if found:
            return found
    return None


@app.command()
def validate(
    source: str = typer.Argument(..., help="Path to converted output directory"),
):
    """Validate a conversion output."""
    from .validation import validate_conversion

    path = Path(source)
    if not path.exists():
        console.print(f"[red]Path not found: {source}[/red]")
        raise typer.Exit(1)

    with console.status("Validating..."):
        report = validate_conversion(path)

    status = "[green]OK[/green]" if report.ok else "[red]FAILED[/red]"
    console.print(f"[bold]Validation Report for {source}[/bold] — {status}")
    console.print(f"  Topics: {report.topics}")
    console.print(f"  Requirements: {report.requirements}")
    console.print(f"  Paragraphs: {report.paragraphs}")
    console.print(f"  Tables: {report.tables}")
    console.print(f"  Images: {report.images}")
    console.print(f"  Unique ERulesIds: {report.unique_erules_ids}")
    if report.source_topic_count is not None:
        console.print(f"  Source topics: {report.source_topic_count}")

    if report.missing_images:
        console.print(
            f"\n[bold yellow]Missing images ({len(report.missing_images)}):[/bold yellow]"
        )
        for m in report.missing_images:
            console.print(f"  - {m}")

    if report.unresolved_references:
        console.print(
            f"\n[bold yellow]Unresolved references "
            f"({len(report.unresolved_references)}):[/bold yellow]"
        )
        for ref in report.unresolved_references[:20]:
            console.print(f"  - {ref}")

    if report.warnings:
        console.print(f"\n[bold yellow]Warnings ({len(report.warnings)}):[/bold yellow]")
        for w in report.warnings[:30]:
            console.print(f"  - {w}")

    if report.errors:
        console.print(f"\n[bold red]Errors ({len(report.errors)}):[/bold red]")
        for e in report.errors:
            console.print(f"  - {e}")

    if not report.ok:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
