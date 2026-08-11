from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from easa_erules import api

FIXTURE = Path("tests/fixtures/cs-vla-sample.xml")


def _version(root: Path, slug: str, data: bytes) -> Path:
    directory = root / "cs-vla" / "versions" / slug
    directory.mkdir(parents=True)
    source = directory / "source.xml"
    source.write_bytes(data)
    (directory / "meta.yaml").write_text(
        yaml.safe_dump(
            {
                "document": "cs-vla",
                "version": {"label": slug, "slug": slug},
                "integrity": {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)},
            }
        ),
        encoding="utf-8",
    )
    return source


def test_two_amendments_have_isolated_indexes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    old = FIXTURE.read_bytes()
    new = old.replace(b"factor of safety", b"safety margin", 1)
    first = _version(tmp_path, "amendment-1", old)
    second = _version(tmp_path, "amendment-2", new)
    assert api.query_regulation("cs-vla", "factor of safety", version="amendment-1")["total"] == 1
    assert api.query_regulation("cs-vla", "safety margin", version="amendment-2")["total"] == 1
    assert first.with_name("search.sqlite").is_file()
    assert second.with_name("search.sqlite").is_file()
    assert first.with_name("search.sqlite") != second.with_name("search.sqlite")
