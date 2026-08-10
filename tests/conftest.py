"""Shared test fixtures and the real-sample gate.

Real EASA publications are not stored in this repository (see
``docs/LEGAL-REVIEW.md``). Tests that need one are marked ``real_sample`` and
skip when the file is absent, so ``pytest`` passes on a clean clone with no
network access.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

REAL_DIR = Path("tests/real_samples")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "real_sample: needs a real EASA publication under tests/real_samples/ "
        "(fetch with: python tests/real_samples/fetch_samples.py)",
    )


def sample_manifests() -> list[Path]:
    """Pinned sample descriptors that ship with the repository."""
    if not REAL_DIR.is_dir():
        return []
    return sorted(REAL_DIR.glob("*.meta.yaml"))


def sample_path(manifest: Path) -> Path:
    """XML path a manifest describes (``cs-vla.meta.yaml`` → ``cs-vla.xml``)."""
    return manifest.with_suffix("").with_suffix(".xml")


def available_samples() -> list[Path]:
    """Locally present sample XML files."""
    return [p for p in (sample_path(m) for m in sample_manifests()) if p.is_file()]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_sha256(manifest: Path) -> str:
    meta = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    return (meta.get("integrity") or {}).get("sha256") or ""


def require_sample(path: Path) -> Path:
    """Skip the calling test unless *path* is present and matches its pin."""
    if not path.is_file():
        pytest.skip(
            f"{path} not present — run: python tests/real_samples/fetch_samples.py"
        )
    manifest = path.with_suffix(".meta.yaml")
    pinned = expected_sha256(manifest) if manifest.is_file() else ""
    if pinned:
        actual = sha256_file(path)
        assert actual == pinned, (
            f"{path.name} does not match its pinned sha256 "
            f"({actual} != {pinned}) — re-fetch the sample"
        )
    return path
