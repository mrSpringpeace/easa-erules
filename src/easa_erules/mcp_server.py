"""MCP server exposing the easa-erules toolkit to agent hosts.

Every tool here is a thin wrapper over :mod:`easa_erules.api`, so an answer
obtained over MCP is identical to the one the CLI would print — same envelope,
same ``source`` provenance, same ``status``.

Run it with::

    easa-erules-mcp

Install the optional dependency first::

    pip install "easa-erules[mcp]"

The scope rules that apply to the CLI skills apply here too and are repeated in
the server instructions: this serves **EASA** requirements only and is not a
source for the FAA certification basis.
"""

from __future__ import annotations

from typing import Any

from . import __version__
from .contract import ToolError

INSTRUCTIONS = """\
Authoritative EASA Easy Access Rules (CS-*, AMC, GM) from local, deterministic
conversion of the official XML publications.

Scope: EASA only. This is NOT a source for the FAA certification basis
(14 CFR Part 23, Part 22 / MOSAIC, FAA ACs). CS material may be offered as
comparative context, but say so explicitly.

Every result carries `schema_version`, `status`, `source` and `warnings`.
`status: no_match` means this document, at this amendment, returned nothing —
it is NOT evidence that a requirement does not exist. Never quote a requirement
without the `designation` and `amendment` from the `source` block.

Prefer `query`, `extract` and `refs` over pulling a whole regulation into
context.
"""


def _build_server() -> Any:
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise SystemExit(
            "The MCP server needs the 'mcp' package.\n"
            "Install it with:  pip install \"easa-erules[mcp]\""
        ) from exc

    from . import api

    server = MCPServer(
        name="easa-erules",
        version=__version__,
        instructions=INSTRUCTIONS,
    )

    def guard(fn: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Turn a typed failure into a payload instead of a transport error."""
        try:
            result: dict[str, Any] = fn(*args, **kwargs)
        except ToolError as exc:
            return exc.to_dict()
        return result

    async def async_guard(fn: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Run the shared synchronous application operation."""
        return guard(fn, *args, **kwargs)

    @server.tool()
    async def list_regulations() -> dict[str, Any]:
        """List the built-in catalog of EASA publications this server can serve."""
        return await async_guard(api.list_regulations)

    @server.tool()
    async def regulation_info(doc_id: str) -> dict[str, Any]:
        """Catalog entry and local cache state for one publication (id or alias)."""
        return await async_guard(api.regulation_info, doc_id)

    @server.tool()
    async def list_cached_versions(
        doc_id: str,
        verify_integrity: bool = False,
    ) -> dict[str, Any]:
        """List cached amendments without network access."""
        return await async_guard(api.list_cached_versions, doc_id, verify_integrity=verify_integrity)

    @server.tool()
    async def list_remote_versions(doc_id: str) -> dict[str, Any]:
        """List XML amendments currently published by EASA."""
        return await async_guard(api.list_remote_versions, doc_id)

    @server.tool()
    async def check_regulation_version(
        doc_id: str,
        version: str,
        deep: bool = False,
    ) -> dict[str, Any]:
        """Verify one cached amendment and compare it with EASA."""
        return await async_guard(api.check_regulation_version, doc_id, version, deep=deep)

    @server.tool()
    async def document_outline(regulation: str, version: str) -> dict[str, Any]:
        """Lightweight ordered navigation tree for a pinned version."""
        return await async_guard(api.document_outline, regulation, version)

    @server.tool()
    async def get_rule_context(
        regulation: str,
        version: str,
        node_id: str | None = None,
        designation: str | None = None,
    ) -> dict[str, Any]:
        """Rule/AMC/GM with breadcrumb, neighbours, relations and references."""
        return await async_guard(
            api.get_rule_context,
            regulation,
            version=version,
            node_id=node_id,
            designation=designation,
        )

    @server.tool()
    async def get_asset(regulation: str, asset_name: str, version: str) -> dict[str, Any]:
        """Return one parser-known asset as base64."""
        return await async_guard(api.get_asset, regulation, asset_name, version)

    @server.tool()
    async def extract_rule(
        regulation: str,
        rule: str,
        version: str | None = None,
        fetch: bool = False,
    ) -> dict[str, Any]:
        """Return one rule, AMC or GM verbatim, by designation (e.g. CS-VLA.303).

        `regulation` is a catalog id/alias (cs-vla) or a local XML path.
        Set `fetch` to download the publication if it is not cached yet.
        """
        return await async_guard(
            api.extract_rule, regulation, rule, version=version, auto_fetch=fetch
        )

    @server.tool()
    async def query_regulation(
        regulation: str,
        query: str,
        limit: int = 20,
        version: str | None = None,
        fetch: bool = False,
        offset: int = 0,
        material_categories: list[str] | None = None,
        structure_kinds: list[str] | None = None,
        within_node_id: str | None = None,
        has_table: bool | None = None,
        has_figure: bool | None = None,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Full-text search within one publication. Use this to find the rule first."""
        return await async_guard(
            api.query_regulation,
            regulation,
            query,
            limit=limit,
            offset=offset,
            material_categories=material_categories,
            structure_kinds=structure_kinds,
            within_node_id=within_node_id,
            has_table=has_table,
            has_figure=has_figure,
            fields=fields,
            version=version,
            auto_fetch=fetch,
        )

    @server.tool()
    async def rule_references(
        regulation: str,
        rule: str,
        version: str | None = None,
        fetch: bool = False,
    ) -> dict[str, Any]:
        """Outgoing and incoming cross-references for a rule."""
        return await async_guard(
            api.rule_references, regulation, rule, version=version, auto_fetch=fetch
        )

    @server.tool()
    async def fetch_regulation(
        doc_id: str,
        version: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Download a publication from EASA into the local cache. Needs network access."""
        return await async_guard(api.fetch_regulation, doc_id, version=version, force=force)

    return server


def main() -> None:
    """Entry point for the ``easa-erules-mcp`` console script (stdio transport)."""
    _build_server().run()


if __name__ == "__main__":
    main()
