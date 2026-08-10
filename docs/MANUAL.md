# easa-erules — User & agent manual

**Version:** 0.2.x  
**Audience:** terminal users and LLM agents working with EASA Easy Access Rules (EAR)

This manual is the full reference. For short agent recipes see [`examples/agent-cookbook.md`](../examples/agent-cookbook.md).

---

## 1. What this tool is

`easa-erules` is a **local, deterministic** toolkit for EASA Easy Access Rules XML publications. It:

- fetches a regulation (or a pinned version) from EASA landing pages,
- reads **Flat OPC** / OOXML packages (including official Word **SDT** packaging),
- builds a **canonical Regulation AST**,
- exports **Markdown**, **JSON**, and **HTML**,
- supports **extract**, **FTS5 query**, **cross-reference graph**, and **validation**.

Regulatory text is **never rewritten by an LLM during conversion**. Models should reason on tool output only.

---

## 2. Install

Requires **Python ≥ 3.11**.

```bash
# users (PyPI)
pip install easa-erules

# development (from clone)
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
# or: pip install -e ".[dev]"
```

Entry point: `easa-erules`.

Verify:

```bash
easa-erules list
# from a clone with dev extras:
pytest -q
```

Publishing / release process: see [`docs/PUBLISHING.md`](PUBLISHING.md).

---

## 3. Concepts

### 3.1 Pipeline

```text
EASA landing page ──fetch──► cache (XML + meta.yaml + sha256)
                              │
Local XML/DOCX ───────────────┤
                              ▼
                     OpcPackage (Flat OPC / ZIP)
                              ▼
              metadata (erules-export customXml + core props)
                              ▼
                     EasaDocumentParser (topics / SDT / body)
                              ▼
                     Regulation AST ──normalize──►
                              ▼
              Markdown · JSON · HTML · FTS5 · refs · validate
```

### 3.2 Designations

Human-readable rule ids used by `extract` / `refs` / frontmatter:

| Pattern | Example |
|---------|---------|
| Letter-code CS | `CS-VLA.1`, `CS-VLA.303` |
| Numeric CS | `CS-23.2000` |
| AMC (letter) | `AMC VLA 1`, `AMC VLA 21(c)` |
| AMC (numbered) | `AMC1 CS-23.2000`, `AMC2 CS-23.2100` |
| GM | `GM1 CS-23.2010` |

On official EAR packages, **opaque ERulesIds** (e.g. `ERULES-1963177438-8056`) are stored as `erules_id` for uniqueness; designations are derived from export `source-title` and first-line titles.

### 3.3 Cache layout

```text
~/.cache/easa-erules/          # override: EASA_ERULES_CACHE
  <doc-id>/
    source.xml
    meta.yaml
    search.sqlite
    versions/<slug>/
      source.xml
      meta.yaml
      original.zip
```

### 3.4 Built-in catalog

**EASA** — `src/easa_erules/sources/easa.yaml`, keyed on stable **landing pages**:

`cs-vla`, `cs-lsa`, `cs-22`, `cs-23`, `cs-25`, `cs-27`, `cs-29`, `cs-e`, `cs-p`, `cs-etso`, `part-21`, `uas-rules`

**FAA** — `src/easa_erules/sources/faa.yaml`, served by the public eCFR API:

`far-21`, `far-23`, `far-25`, `far-27`, `far-43`, `far-91`

FAA versions are eCFR issue dates (`--version 2026-08-05`), not amendment
numbers. With no `--version` the adapter asks eCFR for its latest issue date;
today's date is not a safe default because eCFR lags the calendar.

`.github/workflows/catalog-health.yml` probes every entry weekly and reports
drift as an artifact without failing the build.

---

## 3.5 Output contract

Every machine-readable output carries the same envelope:

```json
{
  "schema_version": "1.0",
  "status": "ok",
  "source": {
    "regulation_id": "cs-vla",
    "designation": "CS-VLA",
    "issue": "unknown",
    "amendment": "Amendment 1",
    "sha256": "…",
    "retrieved_at": "2026-08-10T09:12:00Z",
    "download_url": "…",
    "landing_page": "…",
    "source_path": "…"
  },
  "warnings": ["issue_not_determined"],
  "…": "command-specific payload"
}
```

### `schema_version`

Versioned independently of the package. Policy:

| Change | Effect |
|--------|--------|
| Breaking change to an existing field | major bump |
| New optional field | minor bump |
| Wording or docs only | no bump |

### `source` and the fail-fast rule

Issue and amendment are never silently `null`. When they cannot be established
the field reads `unknown` **and** a warning is emitted (`issue_not_determined`,
`amendment_not_determined`, `provenance_metadata_missing`). An agent quoting a
requirement must be able to tell "no amendment applies" from "nobody knows".

Provenance comes from the `meta.yaml` written by `fetch`. An ad-hoc local file
has no sidecar, so its integrity is computed from the bytes on disk and its
version fields fall back to whatever the document states.

### `status` and exit codes

| `status` | exit | Meaning |
|----------|------|---------|
| `ok` | 0 | Succeeded, results present |
| `no_match` | 0 | Searched, nothing matched |
| `not_cached` | 3 | Regulation not downloaded — run `fetch` or pass `--fetch` |
| `index_missing` | 4 | Search index damaged — retry with `--rebuild` |
| `fetch_failed` | 5 | Download failed |
| `source_drift` | 6 | Landing page no longer matches the catalog entry |
| `parse_error` | 7 | Source could not be parsed |
| `error` | 1 | Everything else (unknown id, bad path) |

`no_match` and `not_cached` are deliberately distinct. An agent that reads an
empty result as "this requirement does not exist" is the most common way an
agent pipeline goes quietly wrong.

---

## 4. CLI reference

| Command | Purpose |
|---------|---------|
| `list` | Built-in regulation catalog |
| `info <id>` | Metadata + cache presence |
| `fetch <id>` | Landing page → download XML → cache + integrity |
| `inspect <id\|path>` | Structure stats, warnings, unknown elements |
| `convert <id\|path> -o DIR` | Markdown / JSON / HTML (`--split`, `--format`) |
| `extract <id\|path> <RULE>` | Single rule (prefer `--format json`) |
| `query <id\|path> "terms"` | Local FTS5 search (`--json`, `--rebuild`) |
| `refs <id\|path> <RULE>` | Outgoing / incoming cross-reference graph |
| `validate DIR` | Check a conversion output directory |

MCP server (optional extra): `easa-erules-mcp` exposes `list_regulations`,
`regulation_info`, `extract_rule`, `query_regulation`, `rule_references` and
`fetch_regulation` over stdio, returning the same envelopes as the CLI.

Most commands accept a **registry id/alias** or a **local path**. Use `--fetch` when the id is not cached yet (where supported).

### Examples

```bash
easa-erules list
easa-erules info vla
easa-erules fetch cs-vla
easa-erules inspect cs-vla
easa-erules convert cs-vla -o ./out --split
easa-erules extract cs-vla CS-VLA.1 --format json
easa-erules query cs-vla "factor of safety" --json
easa-erules refs cs-vla CS-VLA.303 --json
easa-erules validate ./out
```

---

## 5. Metadata sources (real EAR packages)

Official packages expose metadata beyond body text:

1. **`customXml` erules-export document** (`http://www.easa.europa.eu/erules-export`)
   - Document: `source-title`, `guid`, `pub-time`, domain, etc.
   - Per topic: `sdt-id`, `ERulesId`, `source-title`, `TypeOfContent`, `RegulatorySource`, `AmendedBy`, `ParentIR`, dates, …
2. **Word SDT** `w:sdtPr/w:id` linked to export `sdt-id`
3. **`docProps/core.xml`** / **app.xml** — Dublin Core title, created/modified, company

Fixture documents use inline `erules:metadata` elements instead; both paths populate `document.easa_metadata` and per-node `metadata.easa`.

---

## 6. Validation & conversion report

After `convert`, `conversion-report.json` and `easa-erules validate` report:

- topic counts vs source SDT/topic elements,
- duplicate `erules_id` values (should be **empty** on current real samples),
- missing assets, unresolved internal refs,
- empty text nodes and other structure issues.

Philosophy: **no silent content loss** — unknown structures become warnings/errors.

---

## 7. Agent rules of engagement

1. Prefer `query` / `extract` / `refs` with JSON over dumping full regulations into the model context.
2. Never hand-write or “fix” regulatory text from model memory.
3. After bulk `convert`, run `validate`.
4. Ground answers only on tool output; cite designation + source title when answering.
5. If `extract` misses, try `query` then extract the hit’s designation.

Thin skills live under `skills/{generic,codex,claude-code,opencode}/`.

---

## 8. Development & testing

```bash
pytest                                  # offline; real-sample tests skip
python tests/real_samples/fetch_samples.py   # pull the pinned publications
pytest -m real_sample -v
EASA_ERULES_LIVE=1 pytest -k live -v    # network smokes (EASA + eCFR)
ruff check src tests scripts
```

Real EASA publications are **not** stored in this repository — only their pins.
See [`LEGAL-REVIEW.md`](LEGAL-REVIEW.md) and `tests/real_samples/README.md`.

| Suite | Role |
|-------|------|
| `tests/fixtures/` | Synthetic Flat OPC units |
| `tests/golden/` | Frozen MD/JSON/report regressions |
| `tests/real_samples/` | Pinned CS-VLA + CS-23 (fetched, not committed) |
| `tests/test_contract.py` | schema_version, provenance, status/exit codes |
| `tests/test_refdetect.py` | Cross-references detected in plain text |
| `tests/test_faa_adapter.py` | eCFR → shared AST |
| `tests/test_mcp_server.py` | MCP tools match the library results |
| `tests/test_designation.py` | Designation extractor |
| `tests/test_export_metadata.py` | Export customXml + real designations |

### CI

- **CI** (`ci.yml`) — install, ruff, pytest on push/PR, plus a pinned real-sample smoke.
- **Catalog health** (`catalog-health.yml`) — weekly reachability probe of every
  catalog entry; reports drift as an artifact and never fails the build.
- **Live EASA smoke** (`live-smoke.yml`) — manual / weekly fetch of `cs-vla` and `cs-25`.

---

## 9. Multi-authority adapters

```python
from easa_erules.adapters import get_adapter

get_adapter("easa").capabilities()  # production — EAR XML / Flat OPC
get_adapter("faa").capabilities()   # prototype  — 14 CFR via the eCFR API
```

Both land in the same Regulation AST, so `extract`, `query` and `refs` work
against either authority unchanged:

```bash
easa-erules fetch far-23
easa-erules extract far-23 "14 CFR 23.2005"
easa-erules query far-23 "stall speed" --json
```

The eCFR mapping is literal: `DIV5` part → document, `DIV6`/`DIV7` subpart →
section, `DIV8` → requirement with a `14 CFR 23.2000` designation.

There is **no ASTM adapter**. Those standards are paywalled and cannot be
redistributed, so there is nothing an adapter could fetch.

> **Scope warning.** This tool is not a source for the FAA certification basis
> in the sense that matters for certification: the FAA branch mirrors eCFR text
> only, with no Advisory Circulars, no policy, no preamble. Never let CS
> material stand in for an applicable FAA rule — see the `Scope and
> applicability` section in `skills/generic/SKILL.md`.

---

## 10. Design principles

- **Deterministic conversion** — same source + parser version → same AST / ids / exports  
- **No silent content loss** — unknown elements and failed structures are reported  
- **AST in the middle** — no direct XML → Markdown hacks  
- **Agent-first CLI** — stable JSON shapes for extract / query / refs  
- **EASA first** — multi-authority adapters only after EASA designation quality is solid  

---

## 11. Troubleshooting

| Symptom | What to try |
|---------|-------------|
| `extract` finds nothing | `query` for keywords; check designation form (`CS-VLA.1` vs `CS-VLA 1`) |
| Stale search hits | `query … --rebuild` |
| Fetch fails | Check network; run `python scripts/catalog_health.py` to see whether the landing page drifted |
| `no_match` on a rule you expect | Confirm the regulation **and amendment** — `no_match` is not proof of absence |
| `not_cached` (exit 3) | `easa-erules fetch <id>`, or pass `--fetch` |
| Topic count mismatch | Re-fetch; inspect warnings; confirm package is full EAR XML export |
| Large package slow | Use `query`/`extract` instead of full convert; CS-25+ is heavy |

---

## 12. License

MIT — see root `LICENSE`.
