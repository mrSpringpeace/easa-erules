# easa-erules — Project Re-evaluation Report

| Field | Value |
|-------|--------|
| **Date** | 2026-08-09 |
| **Repository** | `easa-erules` (`main`) |
| **HEAD** | `59fcb91` (M10) |
| **Baseline brief** | `PODKLADY/EASA_ERULES_ZADANI_PROJEKTU_2026080_1.txt` |
| **Tests** | 72 passed, 1 skipped |
| **Approx. Python LOC** | ~6.8k under `src/easa_erules/` (52 modules) |

---

## 1. Executive summary

**easa-erules** is a local, deterministic toolkit for EASA Easy Access Rules (EAR) XML publications. It targets humans in the terminal and LLM agents (Codex, Claude Code, OpenCode, etc.).

**Verdict: MVP complete** for the original project goals.

The pipeline works end-to-end:

```text
fetch (landing page → XML) → parse (Flat OPC / DOCX + SDT) → AST
  → normalize → Markdown / JSON / HTML
  → query (SQLite FTS5) / extract / refs / validate
```

Conversion does **not** rewrite regulatory text with an LLM. Agents are expected to consume structured tool output.

Remaining work is **quality and coverage polish**, not missing core architecture.

---

## 2. Progress since initial review (M5–M10)

| Milestone | Theme | Outcome |
|-----------|--------|---------|
| **M5** | Critical bugs | `extract` fix, assets on convert, frontmatter, ZIP rels, deterministic IDs, internal refs |
| **M6** | Validation + goldens | Real validators, conversion-report, frozen golden tests |
| **M7** | Fetch / registry | `easa.yaml`, landing-page resolver, cache + sha256, `fetch` CLI |
| **M8** | Search | SQLite FTS5 index + `query` CLI |
| **M9** | Open topics | HTML, `refs`, normalize pipeline, LLM skills |
| **M10** | Real docs + docs | English README, CS-VLA/CS-23 samples, expanded catalog, table merges, **SDT parsing** |

---

## 3. Spec compliance (vs. original brief)

| Spec area | Status | Notes |
|-----------|--------|--------|
| §1 Pipeline with AST (not direct XML→MD) | **Met** | Full pipeline present |
| §3 CLI (`list`, `info`, `fetch`, `convert`, `extract`, `query`, `validate`) | **Met** | Plus `inspect`, `refs` |
| §4 Source registry (landing pages) | **Met** | YAML catalog; 12 sources |
| §5 Source resolver / download | **Met** | `EasaSourceResolver` + `EasaDownloader` |
| §6 Reproducibility metadata | **Met** | `meta.yaml` with sha256, URLs, retrieved_at |
| §7 OOXML / Flat OPC abstraction | **Met** | ZIP + Flat OPC; OPC `.rels` convention |
| §8 EASA metadata | **Partial** | Strong on fixtures; real SDTs have thinner structured metadata |
| §9 Canonical AST | **Met** | Document / section / requirement / AMC / GM / blocks / inline |
| §10 Inline model | **Met** | Bold, italic, super/sub, hyperlink, internal ref |
| §11 Images | **Met** | Extract, deterministic names, write to `assets/` |
| §12 Tables | **Mostly met** | Simple MD; complex → HTML; colspan/rowspan improved |
| §13 Internal references + `refs` | **Met** | Detection + graph CLI |
| §14 Markdown split export | **Met** | `index.md` + `rules/` + sidecars |
| §15 YAML frontmatter | **Met** | Fenced `---`; stable ids |
| §16 JSON export / extract | **Met** | Agent-friendly extract shape |
| §17 Query / SQLite FTS5 | **Met** | Auto index + invalidation on SHA/parser version |
| §18 Cache | **Met** | `~/.cache/easa-erules/` / `EASA_ERULES_CACHE` |
| §19 `inspect` | **Met** | Stats + warnings |
| §20–21 Validation / no silent loss | **Met** | Report + unknown elements + topic count check |
| §22 Testing | **Met** | Unit + golden + real CS-VLA/CS-23 smokes |
| §23 Stack (Python 3.11+, no Pandoc) | **Met** | lxml, typer, httpx, PyYAML, stdlib sqlite3 |
| §25 LLM skills | **Met** | Thin adapters under `skills/` |
| §26 On-demand agent workflow | **Met** | `query` / `extract` / `refs` without full context dump |
| FAA/ASTM adapters | **Future** | AST designed for multi-source; only EASA implemented |

---

## 4. Technical findings

### 4.1 Real EASA packaging (critical)

Official EAR XML exports do **not** primarily use the simplified `erules:topic` elements used in unit fixtures.

They use **Word Structured Document Tags** (`w:sdt`) with:

- `alias` / `tag` = `topic`
- `alias` / `tag` = `heading`

Namespace for export metadata elsewhere: `http://www.easa.europa.eu/erules-export`.

The parser now supports:

1. Fixture-style custom XML topics (`http://www.easa.europa.eu/erules`)
2. Official SDT topic/heading packaging

**Measured on checked-in samples:**

| Document | Source topic/heading count | AST topics | Topic mismatch |
|----------|----------------------------|------------|----------------|
| CS-VLA   | 355                        | 355        | No |
| CS-23    | 288                        | 288        | No |

### 4.2 Known limitations (accepted for MVP)

1. **Designation heuristics on real SDTs** — Designations are inferred from leading text; some duplicate `erules_id` values appear in validation (reported, not silent).
2. **Structured EASA metadata** on real SDTs is thinner than on fixture `erules:metadata` blocks.
3. **Very large packages** (e.g. CS-25) are in the catalog but not in CI smokes (size / runtime).
4. **Table layout** — Merged cells improved; exotic nested layouts may still need field fixes.
5. **No embeddings / vector search** — intentional for v1.

---

## 5. CLI surface (as of M10)

| Command | Role |
|---------|------|
| `list` | Catalog |
| `info` | Source + cache status |
| `fetch` | Landing page → XML cache |
| `inspect` | Structure / warnings |
| `convert` | MD / JSON / HTML (`--split`) |
| `extract` | Single rule (JSON preferred) |
| `query` | Local FTS5 search |
| `refs` | Cross-reference graph |
| `validate` | Output-dir integrity |

---

## 6. Test posture

| Suite | Role |
|-------|------|
| `tests/fixtures/` | Synthetic Flat OPC units |
| `tests/golden/` | Frozen MD/JSON/report regressions |
| `tests/real_samples/` | Official CS-VLA + CS-23 XML (~11 MB) |
| `tests/test_*.py` | 72 tests green (1 skip: live network) |

Optional live re-fetch:

```bash
EASA_ERULES_LIVE=1 pytest tests/test_real_samples.py -v
```

---

## 7. Built-in source catalog

`src/easa_erules/sources/easa.yaml`:

- **Core:** cs-vla, cs-lsa, cs-22, cs-23  
- **Extended:** cs-25, cs-27, cs-29, cs-e, cs-p, cs-etso  
- **Rules:** part-21, uas-rules  

Landing pages are stable EASA document-library URLs (not fragile direct download links).

---

## 8. Risk register

| Risk | Severity | Mitigation / next step |
|------|----------|------------------------|
| Designation collisions on real docs | Medium | Better regex / bookmark / TOC mapping |
| Incomplete SDT metadata | Medium | Map more SDT properties / customXml if available |
| CS-25+ runtime / memory | Low–Med | Optional smoke; streaming improvements later |
| EASA HTML page layout changes | Medium | Resolver tests with HTML fixtures; monitor fetch |
| Large real samples in git | Low | Documented refresh path; acceptable for this repo size |

---

## 9. Recommended next steps (when work resumes)

Prioritized, not blocking “done for today”:

1. **Designation quality** — Improve extraction for `CS-VLA 1`, AMC/GM variants; reduce duplicate-id noise.  
2. **Real-doc metadata** — Pull more structured fields if present in SDT tags / related parts.  
3. **Optional CI** — Nightly or manual job for CS-25 fetch smoke (`EASA_ERULES_LIVE`).  
4. **Agent examples** — Short end-to-end cookbook in README or `examples/`.  
5. **Future adapters** — FAA/ASTM only after EASA designation quality is solid.

---

## 10. Conclusion

Against the original zadání, **easa-erules delivers a usable MVP**:

- Deterministic conversion pipeline with an intermediate AST  
- Fetch + cache + integrity  
- Markdown / JSON / HTML  
- Search, extract, refs, validation  
- Agent-oriented skills  
- Proven on **real** CS-VLA and CS-23 EAR XML, not only fixtures  

The project is in good shape to pause. Resume with designation/metadata polish and selective broader smoke coverage rather than new architectural layers.

---

*Report authored as session wrap-up for 2026-08-09. See also root `README.md` and `CHANGELOG.md`.*
