from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from easa_erules import api
from easa_erules.contract import Status, ToolError

FIXTURE = Path("tests/fixtures/cs-vla-sample.xml")


def test_one_byte_change_is_integrity_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    directory = tmp_path / "cs-vla" / "versions" / "amendment-1"
    directory.mkdir(parents=True)
    data = FIXTURE.read_bytes()
    source = directory / "source.xml"
    source.write_bytes(data)
    (directory / "meta.yaml").write_text(
        yaml.safe_dump(
            {
                "version": {"label": "Amendment 1", "slug": "amendment-1"},
                "integrity": {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)},
            }
        ),
        encoding="utf-8",
    )
    source.write_bytes(data.replace(b"Factor of safety", b"Factor of safetx", 1))
    inventory = api.list_cached_versions("cs-vla", verify_integrity=True)
    assert inventory["versions"][0]["integrity"]["state"] == "mismatch"
    with pytest.raises(ToolError) as exc:
        api.extract_rule("cs-vla", "CS-VLA.303", version="amendment-1")
    assert exc.value.status is Status.INTEGRITY_ERROR


def test_missing_and_unreadable_metadata_are_distinct(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    for slug in ("amendment-1", "amendment-2"):
        directory = tmp_path / "cs-vla" / "versions" / slug
        directory.mkdir(parents=True)
        (directory / "source.xml").write_bytes(b"x")
    (tmp_path / "cs-vla" / "versions" / "amendment-2" / "meta.yaml").write_text(
        "[broken", encoding="utf-8"
    )
    states = {
        item["version_slug"]: item["integrity"]["state"]
        for item in api.list_cached_versions("cs-vla")["versions"]
    }
    assert states == {
        "amendment-2": "metadata_unreadable",
        "amendment-1": "metadata_missing",
    }
