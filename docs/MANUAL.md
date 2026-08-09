# easa-erules — User & agent manual

**Version:** 0.1.x (MVP + polish)  
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
# recommended
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# or
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Entry point: `easa-erules`.

Verify:

```bash
easa-erules list
pytest -q
```

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

Defined in `src/easa_erules/sources/easa.yaml` (stable **landing pages**):

`cs-vla`, `cs-lsa`, `cs-22`, `cs-23`, `cs-25`, `cs-27`, `cs-29`, `cs-e`, `cs-p`, `cs-etso`, `part-21`, `uas-rules`

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
pytest
pytest tests/test_real_samples.py -v
pytest tests/test_designation.py tests/test_export_metadata.py -v
EASA_ERULES_LIVE=1 pytest tests/test_real_samples.py -k live -v
ruff check src tests
```

| Suite | Role |
|-------|------|
| `tests/fixtures/` | Synthetic Flat OPC units |
| `tests/golden/` | Frozen MD/JSON/report regressions |
| `tests/real_samples/` | Official CS-VLA + CS-23 XML |
| `tests/test_designation.py` | Designation extractor |
| `tests/test_export_metadata.py` | Export customXml + real designations |

### CI

- **CI** (`.github/workflows/ci.yml`) — install, ruff, pytest on push/PR.
- **Live EASA smoke** (`.github/workflows/live-smoke.yml`) — manual / weekly fetch of `cs-vla` and `cs-25` (network).

---

## 9. Multi-authority adapters

```python
from easa_erules.adapters import get_adapter

get_adapter("easa").capabilities()  # production
get_adapter("faa").capabilities()   # scaffold
get_adapter("astm").capabilities()  # scaffold
```

See `src/easa_erules/adapters/README.md`. FAA/ASTM fetch and parse raise `NotImplementedError` until implemented.

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
| Fetch fails | Check network; landing page layout may have changed; open an issue with HTML fixture |
| Topic count mismatch | Re-fetch; inspect warnings; confirm package is full EAR XML export |
| Large package slow | Use `query`/`extract` instead of full convert; CS-25+ is heavy |

---

## 12. License

MIT — see root `LICENSE`.
