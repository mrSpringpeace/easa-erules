#!/usr/bin/env python3
"""Turn a catalog-health report into one GitHub issue, opened or closed.

The weekly catalog-health job is continue-on-error, so drift never turns CI
red. Before 2026-11-06 its only output was an artifact nobody opened; this
script makes drift reach a person:

- drift (or no report at all, or an unreadable publication-history.xml) and
  no open issue labelled ``catalog-drift`` -> open one;
- drift and an open issue -> add the new report as a comment (one issue per
  incident, not one per week);
- no drift and an open issue -> comment that it cleared and close it.

    python scripts/drift_issue.py catalog-health.json --run-url URL
    python scripts/drift_issue.py catalog-health.json --dry-run   # print, call nothing

Uses the ``gh`` CLI (GH_TOKEN in the workflow).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

LABEL = "catalog-drift"
TITLE = "Catalog health: drift detected"


def problems(report: dict[str, Any] | None) -> list[str]:
    """One line per problem; empty when the report is clean."""
    if report is None:
        return ["The job produced no catalog-health.json (the probe step crashed)."]
    lines: list[str] = []
    history = report.get("publication_history") or {}
    if history.get("status") not in (None, "ok"):
        lines.append(f"publication-history.xml: {history.get('status')} — {history.get('detail', '')}")
    for entry in report.get("entries", []):
        if entry.get("status") != "ok":
            lines.append(f"`{entry['id']}` {entry['status']}: {entry.get('detail', '')}")
    return lines


def body(lines: list[str], report: dict[str, Any] | None, run_url: str) -> str:
    checked = (report or {}).get("checked_at", "unknown time")
    mode = "deep" if (report or {}).get("deep") else "resolve-only"
    text = [f"Catalog health ({mode}) at {checked}: {len(lines)} problem(s).", ""]
    text += [f"- {line}" for line in lines]
    text += [
        "",
        f"Run: {run_url}" if run_url else "",
        "",
        "Reproduce locally: `python scripts/catalog_health.py --deep`. "
        "The report is attached to the run as the `catalog-health` artifact.",
    ]
    return "\n".join(text)


def _gh(args: list[str], *, dry_run: bool) -> str:
    if dry_run:
        print("gh " + " ".join(args))
        return ""
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def open_issue_number(*, dry_run: bool) -> int | None:
    if dry_run:
        return None
    out = _gh(
        ["issue", "list", "--label", LABEL, "--state", "open", "--json", "number", "--limit", "1"],
        dry_run=False,
    )
    found = json.loads(out or "[]")
    return int(found[0]["number"]) if found else None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="catalog-health.json written by catalog_health.py")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    path = Path(args.report)
    report = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    lines = problems(report)
    existing = open_issue_number(dry_run=args.dry_run)

    if lines:
        text = body(lines, report, args.run_url)
        if existing is None:
            _gh(["label", "create", LABEL, "--color", "D93F0B", "--force",
                 "--description", "Weekly catalog health found drift"], dry_run=args.dry_run)
            _gh(["issue", "create", "--title", TITLE, "--label", LABEL, "--body", text],
                dry_run=args.dry_run)
            print(f"opened issue: {len(lines)} problem(s)")
        else:
            _gh(["issue", "comment", str(existing), "--body", text], dry_run=args.dry_run)
            print(f"commented on #{existing}: {len(lines)} problem(s)")
        if args.dry_run:
            print(text)
    elif existing is not None:
        note = f"Catalog health is clean again ({(report or {}).get('checked_at', '')}). {args.run_url}"
        _gh(["issue", "close", str(existing), "--comment", note], dry_run=args.dry_run)
        print(f"closed #{existing}")
    else:
        print("clean, no open drift issue")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
