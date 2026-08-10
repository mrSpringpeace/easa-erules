#!/usr/bin/env python3
"""Check that every catalog entry still resolves to a downloadable publication.

Reports drift; does not fix it. A non-zero exit means at least one entry is
broken, but the CI job that runs this is deliberately ``continue-on-error`` —
an EASA website restructure should raise a flag, not block everyone's build.

    python scripts/catalog_health.py                       # human summary
    python scripts/catalog_health.py --output health.json  # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from typing import Any

import httpx

from easa_erules.sources import list_sources
from easa_erules.sources.resolver import EasaSourceResolver

TIMEOUT = 60.0
USER_AGENT = "easa-erules-catalog-health/1.0 (+https://github.com/mrSpringpeace/easa-erules)"


def check_easa(entry: dict[str, Any], resolver: EasaSourceResolver) -> dict[str, Any]:
    """Resolve the landing page and confirm a preferred-format publication exists."""
    result: dict[str, Any] = {
        "id": entry["id"],
        "authority": entry.get("authority", ""),
        "landing_page": entry.get("landing_page", ""),
    }
    try:
        resolved = resolver.resolve(entry["id"])
    except httpx.HTTPError as exc:
        return {**result, "status": "unreachable", "detail": str(exc)[:200]}
    except Exception as exc:  # resolver raises LookupError / ValueError on drift
        return {**result, "status": "drift", "detail": str(exc)[:200]}

    if not resolved.publications:
        return {**result, "status": "drift", "detail": "no publications found on landing page"}
    if not resolved.selected:
        formats = sorted({p.format for p in resolved.publications})
        return {
            **result,
            "status": "drift",
            "detail": f"no {entry.get('preferred_format', 'xml')} publication (found: {formats})",
        }

    return {
        **result,
        "status": "ok",
        "detail": f"{resolved.selected.version_label} ({len(resolved.publications)} publications)",
        "version_label": resolved.selected.version_label,
        "download_url": resolved.selected.download_url,
    }


def check_faa(entry: dict[str, Any], client: httpx.Client) -> dict[str, Any]:
    """Confirm the eCFR versioner still serves this part."""
    from easa_erules.adapters.faa import FaaEcfrAdapter

    adapter = FaaEcfrAdapter()
    result: dict[str, Any] = {"id": entry["id"], "authority": entry.get("authority", "")}
    try:
        issue_date = adapter.latest_issue_date(entry["id"])
    except Exception as exc:
        return {**result, "status": "drift", "detail": f"no issue date: {str(exc)[:120]}"}

    url = adapter.download_url(entry["id"], on_date=issue_date)
    result["landing_page"] = url
    try:
        response = client.head(url)
        if response.status_code >= 400:
            response = client.get(url)
        if response.status_code >= 400:
            return {**result, "status": "drift", "detail": f"HTTP {response.status_code}"}
    except httpx.HTTPError as exc:
        return {**result, "status": "unreachable", "detail": str(exc)[:200]}
    return {**result, "status": "ok", "detail": f"eCFR as of {issue_date}"}


def run() -> dict[str, Any]:
    entries = list_sources()
    results: list[dict[str, Any]] = []

    with (
        EasaSourceResolver(timeout=TIMEOUT) as resolver,
        httpx.Client(
            follow_redirects=True, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as client,
    ):
        for entry in entries:
            authority = str(entry.get("authority", "")).upper()
            if authority == "FAA":
                results.append(check_faa(entry, client))
            else:
                results.append(check_easa(entry, resolver))

    ok = sum(1 for r in results if r["status"] == "ok")
    return {
        "checked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(results),
        "ok": ok,
        "drifted": [r["id"] for r in results if r["status"] != "ok"],
        "entries": results,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="write the JSON report to this path")
    args = parser.parse_args(argv)

    report = run()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)

    print(f"catalog health: {report['ok']}/{report['total']} ok")
    for entry in report["entries"]:
        marker = "ok  " if entry["status"] == "ok" else "DRIFT"
        print(f"  {marker} {entry['id']:<12} {entry.get('detail', '')}")

    return 0 if not report["drifted"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
