"""scripts/drift_issue.py decides when the weekly catalog check needs a human."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "drift_issue", Path(__file__).parent.parent / "scripts" / "drift_issue.py"
)
assert _SPEC and _SPEC.loader
drift_issue = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(drift_issue)


def _report(**entry_overrides: object) -> dict:
    entry = {"id": "cs-vla", "status": "ok", "detail": "Amendment 1"}
    entry.update(entry_overrides)
    return {"checked_at": "2026-11-06T07:08:50Z", "publication_history": {"status": "ok"}, "entries": [entry]}


def test_clean_report_has_no_problems():
    assert drift_issue.problems(_report()) == []


def test_drifted_entry_is_a_problem():
    (line,) = drift_issue.problems(_report(status="drift", detail="history not used"))
    assert "`cs-vla` drift: history not used" in line


def test_missing_report_is_a_problem():
    """A crashed probe must not read as "all clear"."""
    assert drift_issue.problems(None)


def test_unreadable_history_is_a_problem():
    report = _report()
    report["publication_history"] = {"status": "broken", "detail": "HTTP 503"}
    (line,) = drift_issue.problems(report)
    assert "publication-history.xml: broken" in line
