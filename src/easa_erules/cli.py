"""CLI for easa-erules."""

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from .input.package import OpcPackage
from .model import (
    FigureNode,
    HeadingNode,
    ListNode,
    ParagraphNode,
    RegulationDocument,
    RegulationRequirement,
    RegulationSection,
    TableNode,
)
from .parser import parse_easa_document
from .render import render_json, render_markdown

app = typer.Typer(
    name="easa-erules",
    help="Universal toolkit for EASA Easy Access Rules XML publications",
    add_completion=False,
)

console = Console()


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
        table.add_row(key, source["title"], source["type"], ", ".join(source.get("aliases", [])))

    console.print(table)


@app.command()
def info(doc_id: str):
    """Show information about a regulation source."""
    from .sources.registry import REGISTRY

    doc_id = doc_id.lower()
    if doc_id not in REGISTRY:
        console.print(f"[red]Unknown document: {doc_id}[/red]")
        console.print("Use 'easa-erules list' to see available documents.")
        raise typer.Exit(1)

    source = REGISTRY[doc_id]
    console.print(f"[bold cyan]{source['title']}[/bold cyan]")
    console.print(f"  ID: {doc_id}")
    console.print(f"  Type: {source['type']}")
    console.print(f"  Authority: {source['authority']}")
    console.print(f"  Landing page: {source['landing_page']}")
    console.print(f"  Preferred format: {source['preferred_format']}")
    if source.get("aliases"):
        console.print(f"  Aliases: {', '.join(source['aliases'])}")


@app.command()
def inspect(
    source: str = typer.Argument(..., help="Path to XML file or document ID"),
):
    """Inspect an EASA XML document structure."""
    # Load package
    if Path(source).exists():
        package = OpcPackage.from_file(source)
        doc_id = Path(source).stem
    else:
        console.print(f"[red]File not found: {source}[/red]")
        raise typer.Exit(1)

    # Parse
    try:
        doc = parse_easa_document(package)
    except Exception as e:
        console.print(f"[red]Parse error: {e}[/red]")
        raise typer.Exit(1)

    # Collect statistics
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

    # Show EASA metadata
    if doc.metadata.get("easa"):
        console.print("\n[bold]EASA Metadata:[/bold]")
        console.print(JSON.from_data(doc.metadata["easa"]))

    # Show warnings
    if hasattr(package, 'warnings') and package.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for w in package.warnings:
            console.print(f"  - {w}")


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

    def count(node):
        if isinstance(node, RegulationSection):
            stats["Topics/Sections"] += 1
        elif isinstance(node, RegulationRequirement):
            stats["Requirements"] += 1
        elif type(node).__name__ == "GuidanceNode":
            stats["Guidance"] += 1
        elif type(node).__name__ == "AcceptableMeansOfComplianceNode":
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

        for child in getattr(node, 'children', []):
            count(child)

    count(doc)
    return stats


@app.command()
def convert(
    source: str = typer.Argument(..., help="Path to XML file or document ID"),
    output: Path | None = typer.Option(None, "-o", "--output", help="Output directory"),
    split: bool = typer.Option(False, "--split", help="Split output by rule/topic"),
    format: str = typer.Option("markdown", "--format", "-f", help="Output format: markdown, json"),
    asset_prefix: str = typer.Option("assets", "--assets", help="Asset path prefix"),
):
    """Convert EASA XML to Markdown or JSON."""
    # Load package
    if Path(source).exists():
        package = OpcPackage.from_file(source)
        doc_id = Path(source).stem
    else:
        console.print(f"[red]File not found: {source}[/red]")
        raise typer.Exit(1)

    # Parse
    with console.status("Parsing document..."):
        doc = parse_easa_document(package)

    # Render
    with console.status("Rendering output..."):
        if format == "markdown":
            files = render_markdown(doc, split_by_rule=split, asset_prefix=asset_prefix)
        elif format == "json":
            result = render_json(doc)
            files = {f"{doc_id}.json": json.dumps(result, indent=2, ensure_ascii=False)}
        else:
            console.print(f"[red]Unknown format: {format}[/red]")
            raise typer.Exit(1)

    # Write output
    if output:
        output.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            filepath = output / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
        console.print(f"[green]Output written to {output}[/green]")
    else:
        # Print to stdout (first file only for split)
        if split and len(files) > 1:
            console.print(f"[yellow]Split output has {len(files)} files. Use --output to save.[/yellow]")
            for fname in list(files)[:5]:
                console.print(f"  {fname}")
            if len(files) > 5:
                console.print(f"  ... and {len(files) - 5} more")
        else:
            for content in files.values():
                console.print(content)


@app.command()
def extract(
    source: str = typer.Argument(..., help="Path to XML file"),
    rule: str = typer.Argument(..., help="Rule designation (e.g., CS-VLA.303)"),
    format: str = typer.Option("json", "--format", "-f", help="Output format: json, markdown"),
):
    """Extract a single rule by designation."""
    if not Path(source).exists():
        console.print(f"[red]File not found: {source}[/red]")
        raise typer.Exit(1)

    package = OpcPackage.from_file(source)
    doc = parse_easa_document(package)

    # Find rule
    target = _find_rule(doc, rule)
    if not target:
        console.print(f"[red]Rule not found: {rule}[/red]")
        raise typer.Exit(1)

    if format == "json":
        from .render import render_json
        result = render_json(target)
        console.print(JSON.from_data(result))
    else:
        from .render import render_markdown
        files = render_markdown(target)
        for content in files.values():
            console.print(content)


def _find_rule(node: Any, designation: str) -> Any | None:
    """Find a rule by designation."""
    if hasattr(node, 'designation') and node.designation == designation:
        return node
    if hasattr(node, 'erules_id') and node.erules_id == designation:
        return node

    for child in getattr(node, 'children', []):
        result = _find_rule(child, designation)
        if result:
            return result
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

    console.print(f"[bold]Validation Report for {source}[/bold]")
    console.print(f"  Topics: {report.topics}")
    console.print(f"  Paragraphs: {report.paragraphs}")
    console.print(f"  Tables: {report.tables}")
    console.print(f"  Images: {report.images}")

    if report.warnings:
        console.print(f"\n[bold yellow]Warnings ({len(report.warnings)}):[/bold yellow]")
        for w in report.warnings:
            console.print(f"  - {w}")

    if report.errors:
        console.print(f"\n[bold red]Errors ({len(report.errors)}):[/bold red]")
        for e in report.errors:
            console.print(f"  - {e}")

    if report.errors:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()