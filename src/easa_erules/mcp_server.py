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

    @server.tool()
    def list_regulations() -> dict[str, Any]:
        """List the built-in catalog of EASA publications this server can serve."""
        return guard(api.list_regulations)

    @server.tool()
    def regulation_info(doc_id: str) -> dict[str, Any]:
        """Catalog entry and local cache state for one publication (id or alias)."""
        return guard(api.regulation_info, doc_id)

    @server.tool()
    def extract_rule(
        regulation: str,
        rule: str,
        version: str | None = None,
        fetch: bool = False,
    ) -> dict[str, Any]:
        """Return one rule, AMC or GM verbatim, by designation (e.g. CS-VLA.303).

        `regulation` is a catalog id/alias (cs-vla) or a local XML path.
        Set `fetch` to download the publication if it is not cached yet.
        """
        return guard(api.extract_rule, regulation, rule, version=version, auto_fetch=fetch)

    @server.tool()
    def query_regulation(
        regulation: str,
        query: str,
        limit: int = 20,
        version: str | None = None,
        fetch: bool = False,
    ) -> dict[str, Any]:
        """Full-text search within one publication. Use this to find the rule first."""
        return guard(
            api.query_regulation,
            regulation,
            query,
            limit=limit,
            version=version,
            auto_fetch=fetch,
        )

    @server.tool()
    def rule_references(
        regulation: str,
        rule: str,
        version: str | None = None,
        fetch: bool = False,
    ) -> dict[str, Any]:
        """Outgoing and incoming cross-references for a rule."""
        return guard(api.rule_references, regulation, rule, version=version, auto_fetch=fetch)

    @server.tool()
    def fetch_regulation(
        doc_id: str,
        version: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Download a publication from EASA into the local cache. Needs network access."""
        return guard(api.fetch_regulation, doc_id, version=version, force=force)

    return server


def main() -> None:
    """Entry point for the ``easa-erules-mcp`` console script (stdio transport)."""
    _build_server().run()


if __name__ == "__main__":
    main()
