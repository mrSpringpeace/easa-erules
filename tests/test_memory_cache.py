from __future__ import annotations

from pathlib import Path

import pytest

from easa_erules import memory

FIXTURE = Path("tests/fixtures/cs-vla-sample.xml")


def test_lru_is_bounded_to_three_document_versions(tmp_path: Path):
    memory.clear_memory_cache()
    for number in range(4):
        target = tmp_path / f"version-{number}.xml"
        target.write_bytes(FIXTURE.read_bytes())
        memory.parse_cached(target)
    assert memory.memory_cache_info() == {"size": 3, "maxsize": 3}


def test_parse_errors_are_never_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    memory.clear_memory_cache()
    target = tmp_path / "broken.xml"
    target.write_text("broken", encoding="utf-8")
    calls = 0

    def fail(path: Path) -> object:
        nonlocal calls
        calls += 1
        raise ValueError("broken")

    monkeypatch.setattr(memory, "parse_any", fail)
    for _ in range(2):
        with pytest.raises(ValueError):
            memory.parse_cached(target)
    assert calls == 2
    assert memory.memory_cache_info()["size"] == 0
