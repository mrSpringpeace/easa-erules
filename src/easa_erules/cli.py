"""CLI for easa-erules."""

import json
from pathlib import Path
from typing import Any, NoReturn

import typer
import yaml
from rich.console import Console
from rich.json import JSON
from rich.table import Table

from . import __version__
from .api import (
    document_key as _document_key,
)
from .api import (
    extract_rule as api_extract_rule,
)
from .api import (
    fetch_regulation as api_fetch_regulation,
)
from .api import (
    find_rule as _find_rule,
)
from .api import (
    parse_source as _parse_source,
)
from .api import (
    provenance_for as _provenance,
)
from .api import (
    query_regulation as api_query_regulation,
)
from .api import (
    resolve_source_path as _resolve_source_path,
)
from .api import (
    rule_references as api_rule_references,
)
from .contract import SCHEMA_VERSION, Status, ToolError, exit_code
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
from .render import render_html, render_json, render_markdown
from .validation import build_conversion_report, validate_document

app = typer.Typer(
    name="easa-erules",
    help="Universal toolkit for EASA Easy Access Rules XML publications",
    add_completion=False,
)

console = Console()


def _print_json(payload: dict[str, Any]) -> None:
    """Write JSON straight to stdout.

    Not via ``rich`` — it soft-wraps long values and colourises them, which
    turns the output of a piped ``--json`` call into something ``jq`` cannot
    parse. Machine-readable means machine-readable.
    """
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


def _emit(payload: dict[str, Any], status: Status) -> None:
    """Print a machine-readable payload and exit with the matching code."""
    _print_json(payload)
    code = exit_code(status)
    if code:
        raise typer.Exit(code)


def _fail(exc: ToolError, json_out: bool) -> NoReturn:
    """Report a typed failure on the requested channel and exit."""
    if json_out:
        _print_json(exc.to_dict())
    else:
        console.print(f"[red]{exc.message}[/red]")
        from .contract import STATUS_HINTS

        hint = STATUS_HINTS.get(exc.status)
        if hint:
            console.print(f"[dim]{hint}[/dim]")
    raise typer.Exit(exit_code(exc.status))


@app.command("list")
def list_sources_cmd():
    """List available built-in regulation sources."""
    from .sources import list_sources as _list

    table = Table(title="EASA Regulation Sources")
    table.add_column("ID", style="cyan")
    table.add_column("Title", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Aliases", style="dim")

    for source in _list():
        table.add_row(
            source["id"],
            source["title"],
            source["type"],
            ", ".join(source.get("aliases", [])),
        )

    console.print(table)


@app.command()
def info(doc_id: str):
    """Show information about a regulation source (ID or alias)."""
    from .sources import get_source
    from .sources.cache import default_cache_root
    from .sources.downloader import EasaDownloader

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

    downloader = EasaDownloader()
    try:
        cached = downloader.local_source_path(source["id"])
    finally:
        downloader.close()
    if cached:
        console.print(f"  Cached: {cached}")
    else:
        console.print(f"  Cached: [dim]not in {default_cache_root()}[/dim]")


@app.command()
def fetch(
    doc_id: str = typer.Argument(..., help="Document ID or alias (e.g. cs-vla, vla)"),
    version: str | None = typer.Option(
        None, "--version", "-V", help="Pin a version label (e.g. 'Amendment 1')"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Re-download even if cached"),
    json_out: bool = typer.Option(False, "--json", help="Print machine-readable result"),
):
    """Download a publication (EASA or FAA) into the local cache."""
    try:
        with console.status(f"Fetching {doc_id}..."):
            payload = api_fetch_regulation(doc_id, version=version, force=force)
    except ToolError as exc:
        _fail(exc, json_out)

    if json_out:
        _emit(payload, Status.OK)
        return

    result = payload["fetch"]
    prov = payload["source"]
    origin = "cache" if result.get("from_cache") else "download"
    console.print(f"[green]Fetched {result.get('document_id', doc_id)}[/green] ({origin})")
    console.print(f"  Version: {prov['amendment']}")
    console.print(f"  Path: {result.get('source_path', '')}")
    console.print(f"  SHA256: {prov['sha256']}")
    console.print(f"  Download URL: {prov['download_url']}")
    if payload["warnings"]:
        console.print(f"  [yellow]Warnings: {', '.join(payload['warnings'])}[/yellow]")


@app.command()
def inspect(
    source: str = typer.Argument(..., help="Path to XML/DOCX file or document ID"),
    version: str | None = typer.Option(None, "--version", "-V", help="Cached version pin"),
):
    """Inspect an EASA XML document structure."""
    try:
        result, _source_path = _parse_source(source, version=version)
    except ToolError as exc:
        _fail(exc, False)

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


def _write_metadata_yaml(
    output: Path,
    doc: RegulationDocument,
    provenance: dict[str, Any] | None = None,
) -> None:
    """Write metadata.yaml sidecar for split/single conversions."""
    meta = {
        "schema_version": SCHEMA_VERSION,
        "document_id": doc.document_id,
        "title": doc.title,
        "authority": doc.authority or "EASA",
        "version": doc.version,
        "parser_version": __version__,
        "source": provenance,
        "easa": doc.metadata.get("easa") or doc.easa_metadata,
    }
    (output / "metadata.yaml").write_text(
        yaml.dump(meta, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


@app.command()
def convert(
    source: str = typer.Argument(..., help="Path to XML/DOCX file or document ID"),
    output: Path | None = typer.Option(None, "-o", "--output", help="Output directory"),
    split: bool = typer.Option(False, "--split", help="Split output by rule/topic"),
    format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format: markdown, json, html",
    ),
    asset_prefix: str = typer.Option("assets", "--assets", help="Asset path prefix"),
    version: str | None = typer.Option(None, "--version", "-V", help="Cached version pin"),
    fetch_if_missing: bool = typer.Option(
        False,
        "--fetch",
        help="Fetch from EASA if document ID is not in local cache",
    ),
):
    """Convert EASA XML to Markdown or JSON."""
    try:
        with console.status("Parsing document..."):
            result, source_path = _parse_source(
                source, version=version, auto_fetch=fetch_if_missing
            )
    except ToolError as exc:
        _fail(exc, format == "json")

    doc = result.document
    doc_id = source_path.stem
    prov = _provenance(source, source_path, doc).to_dict()

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
            files = render_markdown(
                doc,
                split_by_rule=split,
                asset_prefix=asset_prefix,
                provenance=prov,
            )
        elif format == "json":
            result_json = render_json(doc, result.assets, result.references, provenance=prov)
            files = {
                f"{doc.document_id or doc_id}.json": json.dumps(
                    result_json, indent=2, ensure_ascii=False
                )
            }
        elif format == "html":
            files = render_html(doc, asset_prefix=asset_prefix)
        else:
            console.print(f"[red]Unknown format: {format}[/red]")
            raise typer.Exit(1)

    if output:
        output.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            filepath = output / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")

        # Always emit full JSON AST + metadata for document-oriented formats
        if format in ("markdown", "html"):
            doc_json = render_json(doc, result.assets, result.references, provenance=prov)
            (output / "document.json").write_text(
                json.dumps(doc_json, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            _write_metadata_yaml(output, doc, prov)

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
            provenance=prov,
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
    source: str = typer.Argument(..., help="Path to XML/DOCX file or document ID"),
    rule: str = typer.Argument(..., help="Rule designation (e.g., CS-VLA.303)"),
    format: str = typer.Option(
        "json", "--format", "-f", help="Output format: json, markdown"
    ),
    version: str | None = typer.Option(None, "--version", "-V", help="Cached version pin"),
    fetch_if_missing: bool = typer.Option(
        False,
        "--fetch",
        help="Fetch from EASA if document ID is not in local cache",
    ),
):
    """Extract a single rule by designation."""
    json_out = format == "json"

    if json_out:
        try:
            payload = api_extract_rule(
                source, rule, version=version, auto_fetch=fetch_if_missing
            )
        except ToolError as exc:
            _fail(exc, True)
        _emit(payload, Status(payload["status"]))
        return

    try:
        result, _path = _parse_source(source, version=version, auto_fetch=fetch_if_missing)
    except ToolError as exc:
        _fail(exc, False)

    target = _find_rule(result.document, rule)
    if not target:
        console.print(f"[yellow]Rule not found: {rule}[/yellow]")
        raise typer.Exit(exit_code(Status.NO_MATCH))
    for content in render_markdown(target).values():
        console.print(content)


@app.command()
def refs(
    source: str = typer.Argument(..., help="Path to XML/DOCX file or document ID"),
    rule: str = typer.Argument(..., help="Rule designation (e.g. CS-VLA.303)"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable JSON"),
    version: str | None = typer.Option(None, "--version", "-V", help="Cached version pin"),
    fetch_if_missing: bool = typer.Option(
        False,
        "--fetch",
        help="Fetch from EASA if document ID is not in local cache",
    ),
):
    """Show outgoing and incoming references for a rule."""
    if json_out:
        try:
            payload = api_rule_references(
                source, rule, version=version, auto_fetch=fetch_if_missing
            )
        except ToolError as exc:
            _fail(exc, True)
        _emit(payload, Status(payload["status"]))
        return

    from .model.graph import lookup_refs

    try:
        result, _path = _parse_source(source, version=version, auto_fetch=fetch_if_missing)
    except ToolError as exc:
        _fail(exc, False)

    node = lookup_refs(result.document, rule)
    if not node:
        console.print(f"[yellow]Rule not found: {rule}[/yellow]")
        raise typer.Exit(exit_code(Status.NO_MATCH))

    console.print(node.to_text_tree())
    if node.title:
        console.print(f"[dim]{node.title}[/dim]")


@app.command()
def query(
    source: str = typer.Argument(..., help="Path to XML/DOCX file or document ID"),
    search_text: str = typer.Argument(..., help="Search query (e.g. 'factor of safety')"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of hits"),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable JSON output"),
    rebuild: bool = typer.Option(
        False, "--rebuild", help="Force rebuild of the SQLite search index"
    ),
    version: str | None = typer.Option(None, "--version", "-V", help="Cached version pin"),
    fetch_if_missing: bool = typer.Option(
        False,
        "--fetch",
        help="Fetch from EASA if document ID is not in local cache",
    ),
):
    """Search a regulation using a local SQLite FTS5 index."""
    if json_out:
        try:
            payload = api_query_regulation(
                source,
                search_text,
                limit=limit,
                rebuild=rebuild,
                version=version,
                auto_fetch=fetch_if_missing,
            )
        except ToolError as exc:
            _fail(exc, True)
        _emit(payload, Status(payload["status"]))
        return

    from .search import ensure_index
    from .search import search as run_search

    try:
        source_path = _resolve_source_path(
            source, version=version, auto_fetch=fetch_if_missing
        )
    except ToolError as exc:
        _fail(exc, False)

    document_key = _document_key(source, source_path)

    try:
        with console.status("Indexing (if needed)..."):
            db_path = ensure_index(source_path, document_key=document_key, force=rebuild)
    except Exception as exc:
        _fail(
            ToolError(
                Status.INDEX_MISSING,
                f"Search index could not be built: {exc}",
                source=str(source_path),
            ),
            False,
        )

    result = run_search(db_path, search_text, limit=limit, document_key=document_key)

    console.print(
        f"[bold]{result.title or result.document_id or document_key}[/bold] "
        f"— query: [cyan]{search_text}[/cyan] "
        f"({result.total} hit(s))"
    )
    if not result.hits:
        console.print("[dim]No matches.[/dim]")
        return

    table = Table(show_lines=False)
    table.add_column("Rule", style="cyan", no_wrap=True)
    table.add_column("Type", style="yellow")
    table.add_column("Title", style="green")
    table.add_column("Snippet", style="dim")

    for hit in result.hits:
        table.add_row(
            hit.designation or hit.erules_id or hit.node_id,
            hit.topic_type,
            (hit.title or "")[:60],
            (hit.snippet or hit.text_preview or "").replace("\n", " ")[:100],
        )
    console.print(table)


@app.command()
def validate(
    source: str = typer.Argument(..., help="Path to converted output directory"),
):
    """Validate a conversion output."""
    from .validation import validate_conversion

    path = Path(source)
    if not path.exists():
        _fail(ToolError(Status.ERROR, f"Path not found: {source}", source=source), False)

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
