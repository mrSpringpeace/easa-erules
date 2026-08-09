# easa-erules

**Universal, deterministic toolkit for EASA Easy Access Rules / eRules XML publications.**

This is not “XML → Markdown only”. It is a local CLI for humans and LLM agents:

- fetch a regulation (or a pinned version) from EASA,
- load Flat OPC / OOXML packages,
- parse into a **canonical Regulation AST**,
- export **Markdown**, **JSON**, and **HTML**,
- extract single rules, search with **SQLite FTS5**, explore **cross-references**,
- validate conversions without silently dropping content.

Regulatory text is **never rewritten by an LLM during conversion**. Conversion is deterministic; models should reason on tool output.

---

## Project status

| Area | Status | Notes |
|------|--------|--------|
| Package reader (Flat OPC + ZIP/DOCX) | **Done** | OPC `.rels` paths, relative media targets |
| EASA parser → Regulation AST | **Done** | Fixtures (`erules:topic`) **and** real EAR **Word SDT** topics/headings |
| Deterministic IDs + normalize | **Done** | Stable ids; whitespace/heading/list/ref passes |
| Markdown / JSON / HTML export | **Done** | Split-by-rule MD; frontmatter; HTML document |
| Registry + `fetch` + cache | **Done** | YAML catalog; landing-page resolver; sha256 metadata |
| `extract` / `query` / `refs` | **Done** | Agent-oriented JSON; FTS5 index with invalidation |
| Validation + conversion report | **Done** | Topic count vs source; assets; duplicates; unresolved refs |
| Golden + unit tests | **Done** | Fixtures + frozen goldens |
| Real-document smokes | **Done** | Checked-in `cs-vla.xml` (~6 MB), `cs-23.xml` (~4 MB); topic counts align |
| LLM skills (thin adapters) | **Done** | `skills/{generic,codex,claude-code,opencode}/` |
| Complex tables (colspan/rowspan) | **Improved** | HTML path emits merge attrs; nested tables; header-row fix |
| Broader catalog | **Expanded** | cs-25/27/29, cs-e/p/etso, part-21, uas-rules (+ original four) |
| Designation quality on real docs | **Done** | Export `source-title` + first-line extract; `CS-VLA.1`, `AMC VLA 21(c)`, `AMC1 CS-23.2000`, … |
| Real-doc metadata | **Done** | `erules-export` customXml by `sdt-id`; core props; unique ERulesIds |
| Agent cookbook + manual | **Done** | `examples/agent-cookbook.md`, `docs/MANUAL.md` |
| CI + live CS-25 smoke | **Done** | `.github/workflows/ci.yml` + optional `live-smoke.yml` |
| FAA / ASTM adapters | **Scaffold** | `src/easa_erules/adapters/` — EASA production; FAA/ASTM stubs |
| Vector/embeddings search | **Out of scope** | FTS5 only (by design for v1) |

**Verdict:** **MVP complete** for agent-local EAR workflows, with designation/metadata polish and docs in place. Next expansion is optional (more live packages, FAA/ASTM when needed).
---

## Install

Requires **Python ≥ 3.11**.

```bash
# with uv (recommended)
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# or pip
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Entry point: `easa-erules`.

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
```

Local path **or** registry id/alias is accepted for most commands. Use `--fetch` on convert/extract/query when the id is not cached yet.

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

---

## Architecture

```text
EASA landing page ──fetch──► cache (XML + meta)
                              │
Local XML/DOCX ───────────────┤
                              ▼
                     OpcPackage (Flat OPC / ZIP)
                              ▼
                     EasaDocumentParser
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

Defined in `src/easa_erules/sources/easa.yaml` (stable **landing pages**, not fragile direct URLs):

`cs-vla`, `cs-lsa`, `cs-22`, `cs-23`, `cs-25`, `cs-27`, `cs-29`, `cs-e`, `cs-p`, `cs-etso`, `part-21`, `uas-rules`

---

## For LLM agents

Use the thin skills under `skills/` (generic / Codex / Claude Code / OpenCode).

**Cookbook:** [`examples/agent-cookbook.md`](examples/agent-cookbook.md)  
**Full manual:** [`docs/MANUAL.md`](docs/MANUAL.md)

Rules of engagement:

1. Prefer `query` / `extract` / `refs` with `--json` over stuffing full regulations into context.
2. Never hand-write or “fix” regulatory text from model memory.
3. After bulk `convert`, run `validate`.
4. Ground answers only on tool output.
---

## Development

```bash
pytest
# real EAR smokes (checked-in samples):
pytest tests/test_real_samples.py -v
# optional live network re-fetch:
EASA_ERULES_LIVE=1 pytest tests/test_real_samples.py -v

ruff check src tests
```

- Unit fixtures: `tests/fixtures/`
- Golden renders: `tests/golden/`
- Real documents: `tests/real_samples/` (see README there)

---

## Design principles

- **Deterministic conversion** — same source + parser version → same AST/ids/exports  
- **No silent content loss** — unknown elements and failed structures are reported  
- **AST in the middle** — no direct XML → Markdown hacks  
- **Agent-first CLI** — stable JSON shapes for extract/query/refs  

---

## License

MIT
