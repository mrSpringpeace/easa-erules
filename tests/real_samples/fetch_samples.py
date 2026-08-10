#!/usr/bin/env python3
"""Download the pinned real EASA samples used by the smoke tests.

The publications themselves are not stored in this repository — only the
``*.meta.yaml`` pins (download URL, version label, sha256, size). This script
turns a pin back into a local file and refuses anything whose bytes do not
match.

    python tests/real_samples/fetch_samples.py            # all pinned samples
    python tests/real_samples/fetch_samples.py cs-vla     # one of them
    python tests/real_samples/fetch_samples.py --refresh  # re-pin to latest

``--refresh`` re-resolves the landing page, downloads whatever is current and
rewrites the pin. Use it deliberately: it changes what the smoke tests assert
against.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import zipfile
from pathlib import Path

import httpx
import yaml

HERE = Path(__file__).resolve().parent
USER_AGENT = "easa-erules-tests/1.0 (+https://github.com/mrSpringpeace/easa-erules)"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_xml(data: bytes) -> bytes:
    """EASA serves the XML export as a ZIP; take the largest .xml inside."""
    if data[:2] != b"PK":
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".xml") and not n.endswith("/")]
        if not names:
            raise SystemExit("downloaded ZIP contains no .xml")
        names.sort(key=lambda n: zf.getinfo(n).file_size, reverse=True)
        return zf.read(names[0])


def download(url: str) -> bytes:
    with httpx.Client(follow_redirects=True, timeout=120.0, headers={"User-Agent": USER_AGENT}) as c:
        response = c.get(url)
        response.raise_for_status()
        return response.content


def fetch_pinned(manifest: Path) -> None:
    meta = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    url = (meta.get("source") or {}).get("download_url")
    pinned = (meta.get("integrity") or {}).get("sha256") or ""
    if not url:
        raise SystemExit(f"{manifest.name}: no source.download_url to fetch from")

    target = manifest.with_suffix("").with_suffix(".xml")
    if target.is_file() and pinned and sha256_bytes(target.read_bytes()) == pinned:
        print(f"{target.name}: already present and matching pin")
        return

    print(f"{target.name}: downloading {url}")
    xml = extract_xml(download(url))
    actual = sha256_bytes(xml)
    if pinned and actual != pinned:
        raise SystemExit(
            f"{target.name}: sha256 mismatch — EASA has republished this document.\n"
            f"  pinned: {pinned}\n  actual: {actual}\n"
            f"Re-pin deliberately with --refresh."
        )
    target.write_bytes(xml)
    print(f"{target.name}: {len(xml)} bytes, sha256 {actual}")


def refresh_pin(manifest: Path) -> None:
    """Re-resolve the landing page and rewrite the pin to whatever is current."""
    from easa_erules.sources.resolver import EasaSourceResolver

    meta = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    doc_id = meta.get("document") or manifest.name.split(".")[0]

    with EasaSourceResolver() as resolver:
        resolved = resolver.resolve(doc_id)
    if not resolved.selected:
        raise SystemExit(f"{doc_id}: no XML publication found on {resolved.landing_page}")

    pub = resolved.selected
    xml = extract_xml(download(pub.download_url))
    target = manifest.with_suffix("").with_suffix(".xml")
    target.write_bytes(xml)

    meta["title"] = resolved.title
    meta["version"] = {"label": pub.version_label, "slug": pub.version_slug}
    meta["source"] = {
        "landing_page": resolved.landing_page,
        "download_url": pub.download_url,
        "filename": pub.filename,
        "format": pub.format,
    }
    meta["integrity"] = {"sha256": sha256_bytes(xml), "size": len(xml)}
    manifest.write_text(yaml.dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"{target.name}: re-pinned to {pub.version_label} ({len(xml)} bytes)")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", help="sample ids (default: all pinned)")
    parser.add_argument("--refresh", action="store_true", help="re-pin to the latest publication")
    args = parser.parse_args(argv)

    manifests = sorted(HERE.glob("*.meta.yaml"))
    if args.ids:
        wanted = set(args.ids)
        manifests = [m for m in manifests if m.name.split(".")[0] in wanted]
        if not manifests:
            raise SystemExit(f"no pins matching {sorted(wanted)}")

    for manifest in manifests:
        if args.refresh:
            refresh_pin(manifest)
        else:
            fetch_pinned(manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
