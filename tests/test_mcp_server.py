"""The MCP server must return exactly what the CLI returns."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from easa_erules import api

mcp = pytest.importorskip("mcp", reason="MCP server needs the optional 'mcp' extra")

FIXTURE = Path("tests/fixtures/cs-vla-sample.xml")

EXPECTED_TOOLS = {
    "check_regulation_version",
    "document_outline",
    "list_regulations",
    "list_cached_versions",
    "list_remote_versions",
    "regulation_info",
    "extract_rule",
    "get_asset",
    "get_rule_context",
    "query_regulation",
    "rule_references",
    "fetch_regulation",
}


@pytest.fixture(scope="module")
def server() -> Any:
    from easa_erules.mcp_server import _build_server

    return _build_server()


def _call(server: Any, name: str, args: dict[str, Any]) -> dict[str, Any]:
    result = asyncio.run(server.call_tool(name, args))
    if getattr(result, "structured_content", None):
        return result.structured_content
    return json.loads(result.content[0].text)


def test_exposes_the_agent_operations(server: Any):
    tools = asyncio.run(server.list_tools())
    assert EXPECTED_TOOLS <= {t.name for t in tools}
    for tool in tools:
        assert tool.description, f"{tool.name} has no description"


def test_instructions_carry_the_scope_guardrail(server: Any):
    from easa_erules.mcp_server import INSTRUCTIONS

    text = " ".join(INSTRUCTIONS.split())
    assert "NOT a source for the FAA certification basis" in text
    assert "is NOT evidence that a requirement does not exist" in text
    assert "amendment" in text


def test_extract_matches_the_library_result(server: Any):
    via_mcp = _call(server, "extract_rule", {"regulation": str(FIXTURE), "rule": "CS-VLA.303"})
    direct = api.extract_rule(str(FIXTURE), "CS-VLA.303")
    assert via_mcp == direct
    assert via_mcp["status"] == "ok"
    assert via_mcp["source"]["sha256"]


def test_no_match_comes_back_as_a_payload_not_an_error(server: Any):
    payload = _call(server, "extract_rule", {"regulation": str(FIXTURE), "rule": "CS-VLA.99999"})
    assert payload["status"] == "no_match"
    assert payload["rule"] is None


def test_typed_failure_comes_back_as_a_payload(server: Any):
    payload = _call(server, "extract_rule", {"regulation": "not-a-regulation", "rule": "X"})
    assert payload["status"] == "error"
    assert "error" in payload


def test_catalog_lists_both_authorities(server: Any):
    payload = _call(server, "list_regulations", {})
    authorities = {r["authority"] for r in payload["regulations"]}
    assert {"EASA", "FAA"} <= authorities


def test_rule_context_matches_library_result(server: Any):
    args = {
        "regulation": str(FIXTURE),
        "version": "fixture",
        "designation": "CS-VLA.303",
    }
    via_mcp = _call(server, "get_rule_context", args)
    direct = api.get_rule_context(
        str(FIXTURE), version="fixture", designation="CS-VLA.303"
    )
    assert via_mcp == direct
