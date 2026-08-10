"""Output contract: schema_version, provenance, status codes and exit codes."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from easa_erules import api
from easa_erules.contract import EXIT_CODES, SCHEMA_VERSION, Status, ToolError, envelope
from easa_erules.sources.provenance import UNKNOWN, build_provenance

FIXTURE = Path("tests/fixtures/cs-vla-sample.xml")

AGENT_COMMANDS = ["extract_rule", "query_regulation", "rule_references"]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "easa_erules.cli", *args],
        capture_output=True,
        text=True,
    )


# --- P2: schema_version ----------------------------------------------------


def test_every_agent_command_carries_schema_version():
    payloads = [
        api.extract_rule(str(FIXTURE), "CS-VLA.303"),
        api.rule_references(str(FIXTURE), "CS-VLA.303"),
        api.list_regulations(),
    ]
    for payload in payloads:
        assert payload["schema_version"] == SCHEMA_VERSION


def test_document_render_and_report_carry_schema_version(tmp_path: Path):
    from easa_erules.parsing import parse_any
    from easa_erules.render import render_json
    from easa_erules.validation import validate_document

    result = parse_any(FIXTURE)
    assert render_json(result.document, result.assets, result.references)["schema_version"] == (
        SCHEMA_VERSION
    )
    report = validate_document(result.document, result.assets, result.references)
    assert report.to_dict()["schema_version"] == SCHEMA_VERSION


def test_error_payload_carries_schema_version():
    err = ToolError(Status.NOT_CACHED, "nope")
    assert err.to_dict()["schema_version"] == SCHEMA_VERSION
    assert err.to_dict()["status"] == "not_cached"


# --- P1: provenance --------------------------------------------------------


def test_provenance_block_present_in_agent_outputs():
    payload = api.extract_rule(str(FIXTURE), "CS-VLA.303")
    source = payload["source"]
    for field in ("regulation_id", "issue", "amendment", "sha256", "source_path"):
        assert field in source, field
    assert len(source["sha256"]) == 64


def test_missing_amendment_warns_instead_of_silent_null():
    """A version that cannot be established says so — it never comes back empty."""
    prov = build_provenance(FIXTURE, document_key="cs-vla")
    assert prov.issue == UNKNOWN
    assert prov.amendment == UNKNOWN
    assert "issue_not_determined" in prov.warnings
    assert "amendment_not_determined" in prov.warnings
    assert "provenance_metadata_missing" in prov.warnings

    payload = api.extract_rule(str(FIXTURE), "CS-VLA.303")
    assert payload["source"]["amendment"] == UNKNOWN
    assert "amendment_not_determined" in payload["warnings"]


def test_amendment_read_from_fetch_metadata(tmp_path: Path):
    source = tmp_path / "source.xml"
    source.write_bytes(FIXTURE.read_bytes())
    (tmp_path / "meta.yaml").write_text(
        yaml.dump(
            {
                "document": "cs-vla",
                "title": "Very Light Aeroplanes",
                "version": {"label": "Amendment 1", "slug": "amendment-1"},
                "source": {"download_url": "https://example.invalid/x", "landing_page": "https://e"},
                "retrieved_at": "2026-08-10T00:00:00Z",
                "integrity": {"sha256": "deadbeef", "size": 1},
            }
        ),
        encoding="utf-8",
    )

    prov = build_provenance(source, document_key="cs-vla")
    assert prov.amendment == "Amendment 1"
    assert prov.sha256 == "deadbeef"
    assert prov.retrieved_at == "2026-08-10T00:00:00Z"
    assert "amendment_not_determined" not in prov.warnings


def test_markdown_frontmatter_and_metadata_yaml_carry_source(tmp_path: Path):
    out = tmp_path / "out"
    proc = _run_cli("convert", str(FIXTURE), "-o", str(out), "--split")
    assert proc.returncode == 0, proc.stderr

    meta = yaml.safe_load((out / "metadata.yaml").read_text(encoding="utf-8"))
    assert meta["schema_version"] == SCHEMA_VERSION
    assert meta["source"]["sha256"]

    index = (out / "index.md").read_text(encoding="utf-8")
    front = yaml.safe_load(index.split("---")[1])
    assert front["source"]["regulation_id"]

    report = json.loads((out / "conversion-report.json").read_text(encoding="utf-8"))
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["source"]["sha256"]


# --- P3: status and exit codes --------------------------------------------


def test_exit_code_table_is_complete():
    for status in Status:
        assert status in EXIT_CODES
    assert EXIT_CODES[Status.OK] == 0
    assert EXIT_CODES[Status.NO_MATCH] == 0
    assert EXIT_CODES[Status.NOT_CACHED] == 3
    assert EXIT_CODES[Status.INDEX_MISSING] == 4
    assert EXIT_CODES[Status.FETCH_FAILED] == 5
    assert EXIT_CODES[Status.SOURCE_DRIFT] == 6
    assert EXIT_CODES[Status.PARSE_ERROR] == 7
    assert EXIT_CODES[Status.ERROR] == 1


def test_no_match_is_distinguishable_from_ok():
    hit = api.extract_rule(str(FIXTURE), "CS-VLA.303")
    miss = api.extract_rule(str(FIXTURE), "CS-VLA.99999")
    assert hit["status"] == "ok"
    assert miss["status"] == "no_match"
    assert miss["rule"] is None
    assert "hint" in miss


def test_cli_no_match_exits_zero_with_status():
    proc = _run_cli("extract", str(FIXTURE), "CS-VLA.99999", "--format", "json")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "no_match"


def test_cli_not_cached_exits_three(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    proc = _run_cli("extract", "cs-25", "CS-25.301", "--format", "json")
    assert proc.returncode == EXIT_CODES[Status.NOT_CACHED]
    payload = json.loads(proc.stdout)
    assert payload["status"] == "not_cached"
    assert "fetch" in payload["error"]["hint"]


def test_cli_unknown_source_exits_one():
    proc = _run_cli("extract", "not-a-regulation", "X", "--format", "json")
    assert proc.returncode == EXIT_CODES[Status.ERROR]
    assert json.loads(proc.stdout)["status"] == "error"


def test_cli_parse_error_exits_seven(tmp_path: Path):
    broken = tmp_path / "broken.xml"
    broken.write_text("<not-a-package/>", encoding="utf-8")
    proc = _run_cli("extract", str(broken), "X", "--format", "json")
    assert proc.returncode == EXIT_CODES[Status.PARSE_ERROR]
    assert json.loads(proc.stdout)["status"] == "parse_error"


def test_corrupt_index_reports_index_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A damaged SQLite index is index_missing — recoverable with --rebuild."""
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    from easa_erules.search.indexer import index_db_path

    api.query_regulation(str(FIXTURE), "factor of safety")
    db = index_db_path(FIXTURE.stem)
    db.write_bytes(b"this is not a sqlite database" * 64)

    with pytest.raises(ToolError) as excinfo:
        api.query_regulation(str(FIXTURE), "factor of safety")
    assert excinfo.value.status is Status.INDEX_MISSING
    assert EXIT_CODES[excinfo.value.status] == 4


def test_unparseable_source_reports_parse_error_not_index_missing(tmp_path: Path):
    broken = tmp_path / "broken.xml"
    broken.write_text("<not-a-package/>", encoding="utf-8")
    with pytest.raises(ToolError) as excinfo:
        api.query_regulation(str(broken), "anything")
    assert excinfo.value.status is Status.PARSE_ERROR


# --- machine-readability ---------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ("extract", str(FIXTURE), "CS-VLA.303", "--format", "json"),
        ("refs", str(FIXTURE), "CS-VLA.303", "--json"),
    ],
)
def test_json_output_is_parseable(args: tuple[str, ...]):
    """rich soft-wraps long values; --json must survive a pipe into a parser."""
    proc = _run_cli(*args)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema_version"] == SCHEMA_VERSION


def test_envelope_shape():
    payload = envelope(Status.OK, source={"a": 1}, warnings=["w"], extra=2)
    assert list(payload)[:2] == ["schema_version", "status"]
    assert payload["warnings"] == ["w"]
    assert payload["extra"] == 2
