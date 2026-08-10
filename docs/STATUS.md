# Project status

Development state as of **0.2.0**. This is a working log, not documentation —
for how to use the tool see the [README](../README.md) and the
[manual](MANUAL.md).

## Core pipeline

| Area | Status | Notes |
|------|--------|--------|
| Package reader (Flat OPC + ZIP/DOCX) | **Done** | OPC `.rels` paths, relative media targets |
| EASA parser → Regulation AST | **Done** | Fixtures (`erules:topic`) **and** real EAR **Word SDT** topics/headings |
| Deterministic IDs + normalize | **Done** | Stable, collision-free ids; whitespace/heading/list/ref passes |
| Markdown / JSON / HTML export | **Done** | Split-by-rule MD; frontmatter; HTML document |
| Registry + `fetch` + cache | **Done** | YAML catalogs; landing-page resolver; sha256 metadata |
| `extract` / `query` / `refs` | **Done** | Agent-oriented JSON; FTS5 index with invalidation |
| Validation + conversion report | **Done** | Topic count vs source; assets; duplicates; unresolved refs |
| Golden + unit tests | **Done** | Fixtures + frozen goldens |
| Complex tables (colspan/rowspan) | **Improved** | HTML path emits merge attrs; nested tables; header-row fix |
| Designation quality on real docs | **Done** | Export `source-title` + first-line extract |
| Real-doc metadata | **Done** | `erules-export` customXml by `sdt-id`; core props; unique ERulesIds |
| Vector/embeddings search | **Out of scope** | FTS5 only, by design |

## Agent interface

| Area | Status | Notes |
|------|--------|--------|
| Output contract (`schema_version`, `status`, `source`) | **Done** | 0.2.0; see MANUAL §3.5 |
| Exit codes per status | **Done** | `no_match` 0 · `not_cached` 3 · `index_missing` 4 · `fetch_failed` 5 · `source_drift` 6 · `parse_error` 7 |
| Provenance in every output | **Done** | Amendment/issue fail-fast to `unknown` + warning, never silent `null` |
| Cross-references detected in plain text | **Done** | Official EAR marks few refs up as elements |
| MCP server | **Done** | `easa-erules-mcp`, optional `[mcp]` extra |
| LLM skills (thin adapters) | **Done** | `skills/{generic,codex,claude-code,opencode}/`, incl. FAA scope guardrail |
| Agent cookbook + manual | **Done** | `examples/agent-cookbook.md`, `docs/MANUAL.md` |

## Sources

| Area | Status | Notes |
|------|--------|--------|
| EASA catalog | **12 entries** | cs-vla/lsa/22/23/25/27/29, cs-e/p/etso, part-21, uas-rules |
| FAA catalog | **6 entries** | far-21/23/25/27/43/91 via the public eCFR API |
| FAA adapter | **Prototype** | Fetch + parse + search working; ACs and in-part tables not yet |
| ASTM | **Out of scope** | Paywalled, cannot be redistributed — adapter removed |

## Testing and CI

| Area | Status | Notes |
|------|--------|--------|
| Offline suite | **Green** | `pytest` passes with no network and no samples present |
| Real-document smokes | **Pinned fetch** | Publications no longer committed; `fetch_samples.py` reproduces them by sha256 |
| CI | **Done** | ruff + pytest matrix, adapter smoke, pinned real-sample smoke |
| Catalog health | **Done** | Weekly probe of all 18 entries, reports drift as an artifact |
| Live smoke | **Done** | Manual / weekly `cs-vla` + `cs-25` fetch |

## Open items

1. **Redistribution of EASA text in git history** — awaiting the owner's legal
   assessment. `HEAD` is clean; the blobs remain reachable in history. See
   [LEGAL-REVIEW.md](LEGAL-REVIEW.md).
2. **Package naming** — `easa-erules` no longer describes a toolkit that also
   serves 14 CFR. Rename or split is an owner decision; adoption is still low
   enough that it is cheap now.
3. **FAA coverage** — Advisory Circulars have no structured public API; tables
   and appendices inside parts are currently flattened to paragraphs.
4. **Table edge cases** — exotic nested layouts may still need field fixes.
5. **Large packages** — CS-25 and larger are catalogued but excluded from the
   default smoke matrix on runtime grounds.
