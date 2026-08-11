from pathlib import Path

import pytest

from easa_erules import api
from easa_erules.contract import Status, ToolError
from easa_erules.parsing import parse_any

FIXTURE = Path("tests/fixtures/images.xml")


def test_get_asset_uses_collection_name_not_filesystem_path():
    parsed = parse_any(FIXTURE)
    name = next(iter(parsed.assets.assets))
    payload = api.get_asset(str(FIXTURE), name, "fixture")
    assert payload["asset"]["name"] == name
    assert payload["asset"]["content_base64"]
    with pytest.raises(ToolError) as exc:
        api.get_asset(str(FIXTURE), "../secret", "fixture")
    assert exc.value.status is Status.ERROR
