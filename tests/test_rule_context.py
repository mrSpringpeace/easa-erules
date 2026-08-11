from pathlib import Path

import pytest

from easa_erules import api
from easa_erules.contract import Status, ToolError

FIXTURE = Path("tests/fixtures/cs-vla-sample.xml")


def test_context_has_uniform_item_navigation_relations_and_provenance():
    payload = api.get_rule_context(
        str(FIXTURE), version="fixture", designation="CS-VLA.303"
    )
    assert payload["status"] == "ok"
    assert payload["item"]["material_category"] == "certification_specification"
    assert payload["item"]["plain_text"]
    assert payload["item"]["html"].startswith("<section")
    assert payload["breadcrumb"]
    assert payload["next"]["designation"] == "CS-VLA.305"
    assert set(payload["related"]) == {"requirements", "amc", "gm"}
    assert len(payload["source"]["sha256"]) == 64


def test_context_requires_exactly_one_identifier():
    with pytest.raises(ToolError) as exc:
        api.get_rule_context(str(FIXTURE), version="fixture")
    assert exc.value.status is Status.ERROR


def test_prepare_builds_outline_relations_and_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EASA_ERULES_CACHE", str(tmp_path))
    payload = api.prepare_regulation(str(FIXTURE), "fixture")
    assert payload["status"] == "ok"
    assert payload["preparation"]["navigable_topics"] == 2
    assert Path(payload["preparation"]["search_index"]).is_file()
