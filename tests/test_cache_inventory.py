from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from easa_erules import api
from easa_erules.contract import Status, ToolError


def _write(root: Path, slug: str, body: bytes) -> None:
    directory = root / "cs-vla" / "versions" / slug
    directory.mkdir(parents=True)
    source = directory / "source.xml"
    source.write_bytes(body)
    (directory / "meta.yaml").write_text(
        yaml.safe_dump(
            {
                "version": {"label": slug, "slug": slug},
                "integrity": {"sha256": hashlib.sha256(body).hexdigest(), "size": len(body)},
            }
        ),
        encoding="utf-8",
    )


def test_root_convenience_source_is_not_a_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    _write(tmp_path, "amendment-1", b"one")
    (tmp_path / "cs-vla" / "source.xml").write_bytes(b"one")
    assert len(api.list_cached_versions("cs-vla")["versions"]) == 1


def test_delete_reassigns_latest_and_rejects_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    _write(tmp_path, "amendment-1", b"one")
    _write(tmp_path, "amendment-2", b"two")
    doc = tmp_path / "cs-vla"
    (doc / "latest").write_text("amendment-2\n", encoding="utf-8")
    (doc / "source.xml").write_bytes(b"two")
    (doc / "meta.yaml").write_text("version: {}\n", encoding="utf-8")
    result = api.delete_cached_version("cs-vla", "amendment-2")
    assert result["status"] == "ok"
    assert (doc / "latest").read_text(encoding="utf-8").strip() == "amendment-1"
    assert (doc / "source.xml").read_bytes() == b"one"
    with pytest.raises(ToolError) as exc:
        api.delete_cached_version("cs-vla", "../outside")
    assert exc.value.status in {Status.NOT_CACHED, Status.ERROR}
