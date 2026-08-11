# Project status

Development state as of **0.3.0**. This is a working log, not documentation —
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
| Multi-version inventory + integrity | **Done** | Exact slugs, remote freshness/deep verify, safe deletion |
| `extract` / `query` / `refs` | **Done** | Agent-oriented JSON; FTS5 index with invalidation |
| Outline / rule context / assets | **Done** | Breadcrumbs, neighbours, AMC/GM map, safe fragments |
| Search schema v2 | **Done** | Per-amendment DB, filters, facets, exact total, subtree scope |
| Parse memory LRU | **Done** | Thread-safe, bounded to 3 document versions, explicit invalidation |
| Validation + conversion report | **Done** | Topic count vs source; assets; duplicates; unresolved refs |
| Golden + unit tests | **Done** | Fixtures + frozen goldens |
| Complex tables (colspan/rowspan) | **Improved** | HTML path emits merge attrs; nested tables; header-row fix |
| Designation quality on real docs | **Done** | Export `source-title` + first-line extract |
| Real-doc metadata | **Done** | `erules-export` customXml by `sdt-id`; core props; unique ERulesIds |
| Vector/embeddings search | **Out of scope** | FTS5 only, by design |

## Agent interface

| Area | Status | Notes |
|------|--------|--------|
| Output contract (`schema_version`, `status`, `source`) | **Done** | schema 1.1; see MANUAL §3.5 |
| Exit codes per status | **Done** | Adds `integrity_error` 8 for proven local byte/hash mismatch |
| Provenance in every output | **Done** | Amendment/issue fail-fast to `unknown` + warning, never silent `null` |
| Cross-references detected in plain text | **Done** | Official EAR marks few refs up as elements |
| MCP server | **Done** | `easa-erules-mcp`, optional `[mcp]` extra |
| LLM skills (thin adapters) | **Done** | `skills/{generic,codex,claude-code,opencode}/`, incl. FAA scope guardrail |
| Agent cookbook + manual | **Done** | `examples/agent-cookbook.md`, `docs/MANUAL.md` |

## Sources

| Area | Status | Notes |
|------|--------|--------|
| EASA catalog | **12 entries, all verified** | 10 convert; `cs-p` and `cs-etso` are PDF-only and flagged as such |
| FAA catalog | **6 entries, experimental** | far-21/23/25/27/43/91 via the public eCFR API |
| FAA adapter | **Experimental** | Fetch, parse, search, refs. Tables flattened and images skipped — both reported, never silent. Output shape may change. |
| ASTM | **Out of scope** | Paywalled, cannot be redistributed — adapter removed |

## Testing and CI

| Area | Status | Notes |
|------|--------|--------|
| Offline suite | **Green** | `pytest` passes with no network and no samples present |
| Real-document smokes | **Pinned fetch** | Publications no longer committed; `fetch_samples.py` reproduces them by sha256 |
| CI | **Done** | ruff + pytest matrix, adapter smoke, pinned real-sample smoke |
| Catalog health | **Done, deep** | Weekly resolve + download + parse of all 18 entries; reports drift as an artifact |
| Live smoke | **Done** | Manual / weekly `cs-vla` + `cs-25` fetch |

## Open items

1. **FAA tables and images** — flattened / skipped, and reported as such
   (32 tables and 88 images on 14 CFR 25). Modelling them properly is only
   worth doing if the FAA branch is promoted out of experimental. Advisory
   Circulars have no structured public API at all.
2. **Table edge cases** — exotic nested layouts may still need field fixes.
4. **Large packages** — CS-25 and larger are catalogued but excluded from the
   default smoke matrix on runtime grounds.

## Resolved

- **Catalog verification** (2026-08-10) — all 18 entries checked end to end for
  the first time. Found and fixed: the resolver silently substituted a PDF when
  no XML existed (`cs-p`, `cs-etso`), and the health check reported those as
  green because it never verified the format. Repeated ERulesIds on `part-21`
  and `uas-rules` turned out to be how EASA publishes multi-rule AMC/GM, not a
  parser defect, and are now recorded rather than failed. Narrowing the catalog
  proved unnecessary — it needed verifying, not shrinking.
- **Package naming** (2026-08-10) — kept as `easa-erules`. EASA remains the
  maintained branch and the name is what people searching for Easy Access Rules
  will find; the FAA branch is labelled experimental instead. Revisit only if
  FAA is ever promoted to production, while adoption is still low.
- **Redistribution of EASA text** (2026-08-10) — EASA's copyright policy
  authorises reproduction with acknowledgement, and the "Official Publication"
  clause is a disclaimer, not a copyright carve-out. History is not being
  rewritten; the MIT scope is bounded by the root `NOTICE`. Publications stay
  out of the repository on engineering grounds. See
  [LEGAL-REVIEW.md](LEGAL-REVIEW.md).
