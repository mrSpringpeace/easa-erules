# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1] - 2026-08-09

### Added
- **Designation quality:** robust extract/normalize for `CS-VLA.1`, `CS 23.2000` → `CS-23.2000`, `AMC VLA 21(c)`, `AMC1 23.2000` → `AMC1 CS-23.2000`, GM variants; first-line / export-title based (no full-body false positives).
- **Real-doc metadata:** parse official `erules-export` customXml (topics by `sdt-id`, `ERulesId`, TypeOfContent, RegulatorySource, ParentIR, …) plus `docProps/core.xml` / app properties.
- **CI:** `.github/workflows/ci.yml` (pytest + ruff); `.github/workflows/live-smoke.yml` (manual/weekly `cs-vla` + `cs-25` network smoke).
- **Docs:** `examples/agent-cookbook.md`, `docs/MANUAL.md` (full user/agent manual).
- **Adapters scaffold:** `easa_erules.adapters` with production EASA adapter and FAA/ASTM stubs.
- Tests: `test_designation.py`, `test_export_metadata.py`; live parametrized smokes for `cs-vla` / `cs-25`.

### Fixed
- Duplicate `erules_id` noise on real CS-VLA/CS-23 (unique export ERulesIds; designations no longer collapse to bare `CS-VLA` / `CS-23`).
- Parenthetical AMC designations (`AMC VLA 21(c)` vs truncated `AMC VLA 21`).

## [0.1.0] - 2026-08-08

### Added
- Initial project scaffolding.
- Milestone 1: EASA XML / Flat OPC package reader, EASA Parser, Canonical Regulation AST, Markdown Renderer, CLI (`inspect`, `convert`).
- Milestone 2: Inline formatting, lists, hyperlinks scaffolding, internal reference model.
- Milestone 3: Asset extraction and image parsing.
- Milestone 4: Validation framework skeleton and conversion report.
- Milestone 6: Real validation package (`structure`, `links`, `assets`, `output`, `report`), richer `conversion-report.json`, source topic-count check, golden tests under `tests/golden/`.
- Milestone 7: YAML source catalog (`sources/easa.yaml`), `EasaSourceResolver` (landing-page discovery), `fetch` CLI with cache + sha256 metadata, unified path/doc-id resolution for convert/inspect/extract.
- Milestone 8: Local SQLite FTS5 search (`search/` indexer + query), `query` CLI with JSON output, index invalidation on source SHA / parser version.
- Milestone 9: HTML renderer, `refs` cross-reference graph CLI, AST normalize pipeline, LLM skill adapters, optional real-sample smoke tests.
- Milestone 10: English README + status re-evaluation; expanded registry (cs-25/27/29, cs-e/p/etso, part-21, uas); real CS-VLA/CS-23 samples; table colspan/rowspan HTML + nested tables; header-row parsing fix.

### Fixed (Milestone 5)
- `extract` CLI no longer crashes (`parse_easa_document` import).
- ZIP/DOCX package relationships load from `word/_rels/document.xml.rels` (OPC convention).
- Part path resolution handles relative relationship targets (`media/…`, `../media/…`).
- `convert -o` writes binary assets, `document.json`, and `metadata.yaml`.
- Markdown YAML frontmatter is fenced with `---` and uses stable `erules_id` / designation IDs.
- Topic nested EASA metadata maps camelCase XML names to model fields (no longer empty in frontmatter).
- Deterministic AST node IDs (no random UUIDs).
- Plain-text internal regulatory references detected and resolved when possible.
- Rule-based figure asset names (`cs-test-400-fig-01.png`).
- `info` resolves registry aliases (`vla`, `csvla`, `CS23`, …).
- Conversion report counts topics; validate flags missing image files.
- Dependency fix: replace non-existent `typer[all]` with `typer` + `rich`.
