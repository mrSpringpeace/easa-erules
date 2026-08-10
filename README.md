# easa-erules

[![CI](https://github.com/mrSpringpeace/easa-erules/actions/workflows/ci.yml/badge.svg)](https://github.com/mrSpringpeace/easa-erules/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/easa-erules.svg)](https://pypi.org/project/easa-erules/)
[![Python versions](https://img.shields.io/pypi/pyversions/easa-erules.svg)](https://pypi.org/project/easa-erules/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/mrSpringpeace/easa-erules)](https://github.com/mrSpringpeace/easa-erules/releases)

**Deterministic, local toolkit for airworthiness regulations — built for LLM agents.**

Turns official publications into structured data an agent can quote from:
EASA Easy Access Rules (CS-*, AMC, GM) from the EAR XML exports, and 14 CFR
from the public eCFR API.

- fetch a regulation, or a pinned version, into a local cache
- parse into a **canonical Regulation AST** (Flat OPC / OOXML, or eCFR XML)
- export **Markdown**, **JSON** and **HTML**
- **extract** one rule, **query** with SQLite FTS5, walk **cross-references**
- **validate** conversions so nothing is dropped silently

Regulatory text is **never rewritten by an LLM during conversion**. Conversion
is deterministic; models reason on tool output, not on recall.

Every machine-readable result states which publication and amendment it came
from, and distinguishes "searched, found nothing" from "never looked" — the
usual way an agent pipeline goes quietly wrong.

---

## Install

Requires **Python ≥ 3.11**.

```bash
# PyPI (recommended for users)
pip install easa-erules

# or with uv
uv pip install easa-erules
```

From source / development:

```bash
git clone https://github.com/mrSpringpeace/easa-erules.git
cd easa-erules
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
# or: pip install -e ".[dev]"
```

Pinned git tag (if PyPI is unavailable):

```bash
pip install "git+https://github.com/mrSpringpeace/easa-erules.git@v0.2.0"
```

Optional MCP server (for agent hosts that speak MCP rather than shell):

```bash
pip install "easa-erules[mcp]"
```

Entry points: `easa-erules`, `easa-erules-mcp`.

> **Disclaimer:** Unofficial toolkit. Always verify critical interpretations against the official EASA Easy Access Rules publication. This software does not re-license regulatory text.

---

## Quick start

```bash
# Catalog
easa-erules list
easa-erules info vla

# Download latest XML into the cache
easa-erules fetch cs-vla
easa-erules fetch cs-vla --version "Amendment 1"

# Inspect / convert / extract / search / refs
easa-erules inspect cs-vla
easa-erules convert cs-vla -o ./out --split
easa-erules convert ./local.xml -o ./out --format html
easa-erules extract cs-vla CS-VLA.303 --format json
easa-erules query cs-vla "factor of safety" --json
easa-erules refs cs-vla CS-VLA.303 --json
easa-erules validate ./out

# FAA parts work the same way
easa-erules fetch far-23
easa-erules extract far-23 "14 CFR 23.2005" --format json
```

Local path **or** registry id/alias is accepted for most commands. Use `--fetch` on convert/extract/query when the id is not cached yet.

### Output contract

Every `--json` result carries the same envelope, so an agent can branch on it
without guessing:

```json
{
  "schema_version": "1.0",
  "status": "ok",
  "source": {"regulation_id": "cs-vla", "amendment": "Amendment 1", "sha256": "…"},
  "warnings": [],
  "rule": { "…": "…" }
}
```

| `status` | exit | Meaning |
|----------|------|---------|
| `ok` | 0 | Succeeded, results present |
| `no_match` | 0 | Searched, nothing matched |
| `not_cached` | 3 | Not downloaded — run `fetch` or pass `--fetch` |
| `index_missing` | 4 | Search index damaged — retry with `--rebuild` |
| `fetch_failed` | 5 | Download failed |
| `source_drift` | 6 | Landing page no longer matches the catalog entry |
| `parse_error` | 7 | Source could not be parsed |
| `error` | 1 | Unknown id, bad path, everything else |

`no_match` is **not** evidence that a requirement does not exist. Amendment and
issue are never silently `null`: when they cannot be established the field reads
`unknown` and a warning says so.

### Cache layout

```text
~/.cache/easa-erules/          # override: EASA_ERULES_CACHE
  cs-vla/
    source.xml                 # latest convenience copy
    meta.yaml
    search.sqlite              # FTS index (built on first query)
    versions/<slug>/
      source.xml
      meta.yaml                # sha256, download_url, retrieved_at, …
      original.zip
```

### Split convert output

```text
out/
├── index.md
├── metadata.yaml
├── document.json
├── conversion-report.json
├── rules/
│   └── cs-vla-303.md
└── assets/
    └── cs-vla-303-fig-01.png
```

---

## CLI reference

| Command | Purpose |
|---------|---------|
| `list` | Built-in regulation catalog |
| `info` | Metadata + cache presence for an id/alias |
| `fetch` | Resolve landing page → download XML → cache + integrity |
| `inspect` | Structure stats, warnings, unknown elements |
| `convert` | Markdown / JSON / HTML (`--split`, `--format`) |
| `extract` | Single rule (JSON preferred for agents) |
| `query` | Local FTS5 search (`--json`, `--rebuild`) |
| `refs` | Outgoing / incoming cross-reference graph |
| `validate` | Check a conversion output directory |

Design principles, adapters and the full output contract: [`docs/MANUAL.md`](docs/MANUAL.md).

---

## Architecture

```text
EASA landing page ──fetch──► cache (XML + meta + sha256)
eCFR API          ──fetch──►      │
                                  │
Local XML/DOCX ───────────────────┤
                                  ▼
                     OpcPackage / eCFR XML
                              ▼
              EasaDocumentParser | FaaEcfrAdapter
                              ▼
                     Regulation AST ──normalize──►
                              ▼
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
          Markdown          JSON            HTML
              │
              ├── SQLite FTS5 (query)
              ├── Reference graph (refs)
              └── Validation / conversion-report.json
```

---

## Built-in sources

**EASA** — `sources/easa.yaml`, keyed on stable landing pages rather than
fragile direct URLs:

`cs-vla`, `cs-lsa`, `cs-22`, `cs-23`, `cs-25`, `cs-27`, `cs-29`, `cs-e`, `cs-p`, `cs-etso`, `part-21`, `uas-rules`

**FAA** — `sources/faa.yaml`, served by the public eCFR API:

`far-21`, `far-23`, `far-25`, `far-27`, `far-43`, `far-91`

A weekly workflow probes every entry and reports drift without failing the build:

```bash
python scripts/catalog_health.py
```

---

## For LLM agents

Two integration routes, same results:

- **Shell** — the thin skills under `skills/` (generic / Codex / Claude Code / OpenCode)
- **MCP** — `easa-erules-mcp`, exposing `list_regulations`, `regulation_info`,
  `extract_rule`, `query_regulation`, `rule_references`, `fetch_regulation`

**Cookbook:** [`examples/agent-cookbook.md`](examples/agent-cookbook.md)  
**Full manual:** [`docs/MANUAL.md`](docs/MANUAL.md)

Rules of engagement:

1. Prefer `query` / `extract` / `refs` with `--json` over stuffing full regulations into context.
2. Never hand-write or "fix" regulatory text from model memory.
3. After bulk `convert`, run `validate`.
4. Ground answers only on tool output, and cite the `designation` + `amendment` from the `source` block.
5. This is an **EASA** source. It is not a source for the FAA certification
   basis — the FAA branch mirrors eCFR text only, with no Advisory Circulars or
   policy material.

---

## Development

```bash
pytest                                        # offline; real-sample tests skip
python tests/real_samples/fetch_samples.py    # pull the pinned publications
pytest -m real_sample -v
EASA_ERULES_LIVE=1 pytest -k live -v          # network smokes

ruff check src tests scripts
```

- Unit fixtures: `tests/fixtures/`
- Golden renders: `tests/golden/`
- Real documents: pinned, **not committed** — see `tests/real_samples/README.md`
  and [`docs/LEGAL-REVIEW.md`](docs/LEGAL-REVIEW.md)

**Development state:** [`docs/STATUS.md`](docs/STATUS.md)

---

## Design principles

- **Deterministic conversion** — same source + parser version → same AST/ids/exports  
- **No silent content loss** — unknown elements and failed structures are reported  
- **AST in the middle** — no direct XML → Markdown hacks  
- **Agent-first CLI** — versioned, self-describing JSON for extract/query/refs
- **Explicit over empty** — a result never leaves an agent guessing why it is empty

---

## License

MIT
