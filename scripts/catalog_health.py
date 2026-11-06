#!/usr/bin/env python3
"""Check that every catalog entry still resolves, downloads and parses.

A resolver that finds *a* publication is not evidence the entry works: CS-ETSO
resolved happily for months and handed back a PDF labelled as the XML export.
So `--deep` does the whole thing — download, parse, validate — and reports what
actually came out.

    python scripts/catalog_health.py                       # resolve only, fast
    python scripts/catalog_health.py --deep                # + download and parse
    python scripts/catalog_health.py --deep --output h.json
    python scripts/catalog_health.py --deep --only cs-vla,cs-23

Since 2026-11-06 the resolver reads versions from EASA's
publication-history.xml. Each EASA entry is additionally checked for:

- history_used: the resolver took its versions from the history, not from the
  landing-page fallback (a fallback means the history broke or lost the code);
- format_claim: xml_available / preferred_format agree with the live history
  (catalog_format_problem; CS-ETSO went from PDF-only to XML with Amdt 17);
- landing_page_check: the latest XML on the landing page names the same version
  as the latest XML in the history (landing_page_agrees).

Reports drift; does not fix it. A non-zero exit means at least one entry is
broken, but the CI job that runs this is deliberately continue-on-error — an
EASA website restructure should raise a flag, not block everyone's build.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from easa_erules.sources import list_sources
from easa_erules.sources.history import (
    PUBLICATION_HISTORY_URL,
    HistoryEntry,
    PublicationHistoryFormatError,
    catalog_format_problem,
    parse_publication_history,
)
from easa_erules.sources.resolver import EasaSourceResolver, landing_page_agrees

TIMEOUT = 120.0
USER_AGENT = "easa-erules-catalog-health/1.0 (+https://github.com/mrSpringpeace/easa-erules)"


def _parse_and_validate(path: Path) -> dict[str, Any]:
    """Parse a downloaded publication and summarise what came out."""
    from easa_erules.parsing import parse_any
    from easa_erules.validation import validate_document

    result = parse_any(path)
    report = validate_document(
        result.document,
        result.assets,
        result.references,
        source_topic_count=result.source_topic_count,
    )
    return {
        "topics": report.topics,
        "source_topics": result.source_topic_count,
        "topic_count_mismatch": report.topic_count_mismatch,
        "conflicting_erules_ids": len(report.duplicate_erules_ids),
        "repeated_erules_ids": len(report.repeated_erules_ids),
        "internal_references": report.internal_references,
        "document_title": (result.document.title or "")[:80],
    }


def fetch_history(client: httpx.Client) -> tuple[list[HistoryEntry] | None, dict[str, Any]]:
    """Download and parse publication-history.xml once for the whole run."""
    import hashlib

    summary: dict[str, Any] = {"url": PUBLICATION_HISTORY_URL}
    try:
        response = client.get(PUBLICATION_HISTORY_URL)
        response.raise_for_status()
        entries = parse_publication_history(response.content, base_url=str(response.url))
    except (httpx.HTTPError, PublicationHistoryFormatError) as exc:
        return None, {**summary, "status": "broken", "detail": str(exc)[:200]}
    summary.update(
        status="ok",
        sha256=hashlib.sha256(response.content).hexdigest(),
        entries=len(entries),
        domains=len({entry.domain for entry in entries}),
        newest_generation=max(entry.generated_at for entry in entries),
    )
    return entries, summary


def _history_checks(
    entry: dict[str, Any],
    resolver: EasaSourceResolver,
    resolved: Any,
    history: list[HistoryEntry] | None,
) -> list[str]:
    """Problems with the history side of one EASA entry; empty when fine."""
    problems: list[str] = []
    if entry.get("ear_codes") and resolved.inventory != "publication_history":
        problems.append("history not used: " + "; ".join(resolved.warnings)[:160])
    if history is not None:
        problem = catalog_format_problem(entry, history)
        if problem:
            problems.append(f"format claim: {problem}")
    return problems


def _landing_page_check(
    entry: dict[str, Any], resolver: EasaSourceResolver, history_pub: Any
) -> dict[str, Any]:
    """Compare the landing page's latest XML with the history's latest XML."""
    try:
        landing_pubs = resolver.discover_publications(entry["landing_page"])
        landing = resolver.select_publication(landing_pubs, preferred_format="xml")
    except httpx.HTTPError as exc:
        return {"state": "unreachable", "detail": str(exc)[:160]}
    except LookupError as exc:
        return {"state": "disagrees", "detail": f"landing page: {str(exc)[:140]}"}
    if landing is None:
        return {"state": "disagrees", "detail": "landing page lists no XML"}
    state = "agrees" if landing_page_agrees(landing, history_pub) else "disagrees"
    return {
        "state": state,
        "landing_version": landing.version_label,
        "landing_filename": landing.filename,
        "history_version": history_pub.version_label,
        "history_file_name": history_pub.history_file_name,
    }


def check_easa(
    entry: dict[str, Any],
    resolver: EasaSourceResolver,
    *,
    deep: bool,
    history: list[HistoryEntry] | None = None,
) -> dict[str, Any]:
    """Resolve, cross-check the two inventories, and optionally download and parse."""
    preferred = str(entry.get("preferred_format") or "xml")
    result: dict[str, Any] = {
        "id": entry["id"],
        "authority": entry.get("authority", ""),
        "landing_page": entry.get("landing_page", ""),
        "preferred_format": preferred,
    }
    try:
        resolved = resolver.resolve(entry["id"])
    except httpx.HTTPError as exc:
        return {**result, "status": "unreachable", "detail": str(exc)[:200]}
    except Exception as exc:  # LookupError on drift or missing format
        return {**result, "status": "drift", "detail": str(exc)[:200]}

    pub = resolved.selected
    if pub is None:
        return {**result, "status": "drift", "detail": "no publication selected"}
    if pub.format != preferred:
        return {
            **result,
            "status": "drift",
            "detail": f"selected format {pub.format!r}, catalog expects {preferred!r}",
        }

    result["version_label"] = pub.version_label
    result["download_url"] = pub.download_url
    result["inventory"] = resolved.inventory
    result["resolver_warnings"] = list(resolved.warnings)
    detail = f"{pub.version_label} ({len(resolved.publications)} publications, {resolved.inventory})"

    problems = _history_checks(entry, resolver, resolved, history)
    if preferred == "xml" and resolved.inventory == "publication_history":
        landing_check = _landing_page_check(entry, resolver, pub)
        result["landing_page_check"] = landing_check
        if landing_check["state"] == "disagrees":
            problems.append(
                "landing page disagrees: "
                f"{landing_check.get('landing_version', '')} / {landing_check.get('landing_filename', '')} "
                f"vs history {landing_check.get('history_version', '')}"
                if "landing_version" in landing_check
                else str(landing_check.get("detail", ""))
            )
    if problems:
        return {**result, "status": "drift", "detail": f"{detail} — " + "; ".join(problems)}

    if not deep or preferred != "xml":
        skipped = " — not XML, parse skipped" if preferred != "xml" else ""
        return {**result, "status": "ok", "detail": detail + skipped}

    try:
        from easa_erules.sources import EasaDownloader

        with tempfile.TemporaryDirectory() as tmp:
            with EasaDownloader(cache_root=Path(tmp)) as downloader:
                fetched = downloader.fetch(entry["id"])
            parsed = _parse_and_validate(fetched.source_path)
    except Exception as exc:
        return {
            **result,
            "status": "broken",
            "detail": f"{detail} — {type(exc).__name__}: {str(exc)[:160]}",
        }

    result.update(parsed)
    if parsed["topic_count_mismatch"] or parsed["conflicting_erules_ids"]:
        return {
            **result,
            "status": "broken",
            "detail": f"{detail} — topics {parsed['topics']}/{parsed['source_topics']}, "
            f"{parsed['conflicting_erules_ids']} conflicting ERulesIds",
        }
    return {**result, "status": "ok", "detail": f"{detail} — {parsed['topics']} topics"}


def check_faa(entry: dict[str, Any], client: httpx.Client, *, deep: bool) -> dict[str, Any]:
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
    result["version_label"] = f"eCFR as of {issue_date}"

    try:
        response = client.head(url)
        if response.status_code >= 400:
            response = client.get(url)
        if response.status_code >= 400:
            return {**result, "status": "drift", "detail": f"HTTP {response.status_code}"}
    except httpx.HTTPError as exc:
        return {**result, "status": "unreachable", "detail": str(exc)[:200]}

    if not deep:
        return {**result, "status": "ok", "detail": f"eCFR as of {issue_date}"}

    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = adapter.fetch(entry["id"], version=issue_date, cache_root=Path(tmp))
            parsed = _parse_and_validate(path)
    except Exception as exc:
        return {
            **result,
            "status": "broken",
            "detail": f"{type(exc).__name__}: {str(exc)[:160]}",
        }

    result.update(parsed)
    return {**result, "status": "ok", "detail": f"eCFR {issue_date} — {parsed['topics']} topics"}


def run(*, deep: bool = False, only: set[str] | None = None) -> dict[str, Any]:
    entries = [e for e in list_sources() if not only or e["id"] in only]
    results: list[dict[str, Any]] = []
    history_summary: dict[str, Any] = {}

    with (
        EasaSourceResolver(timeout=TIMEOUT) as resolver,
        httpx.Client(
            follow_redirects=True, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as client,
    ):
        history, history_summary = fetch_history(client)
        for entry in entries:
            authority = str(entry.get("authority", "")).upper()
            if authority == "FAA":
                results.append(check_faa(entry, client, deep=deep))
            else:
                results.append(check_easa(entry, resolver, deep=deep, history=history))

    ok = sum(1 for r in results if r["status"] == "ok")
    return {
        "checked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "deep": deep,
        "total": len(results),
        "ok": ok,
        "drifted": [r["id"] for r in results if r["status"] != "ok"],
        "publication_history": history_summary,
        "entries": results,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="write the JSON report to this path")
    parser.add_argument(
        "--deep",
        action="store_true",
        help="download and parse each entry, not just resolve it",
    )
    parser.add_argument("--only", help="comma-separated catalog ids to check")
    args = parser.parse_args(argv)

    only = {s.strip() for s in args.only.split(",")} if args.only else None
    report = run(deep=args.deep, only=only)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)

    mode = "deep" if report["deep"] else "resolve-only"
    print(f"catalog health ({mode}): {report['ok']}/{report['total']} ok")
    history = report["publication_history"]
    print(
        f"  publication-history.xml: {history.get('status')} "
        f"{history.get('entries', '')} entries, newest {history.get('newest_generation', '')} "
        f"{history.get('detail', '')}"
    )
    for entry in report["entries"]:
        marker = "ok   " if entry["status"] == "ok" else entry["status"].upper()
        print(f"  {marker:<12} {entry['id']:<12} {entry.get('detail', '')}")

    return 0 if not report["drifted"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
