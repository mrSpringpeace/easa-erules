# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-08-08

### Added
- Initial project scaffolding.
- Milestone 1: EASA XML / Flat OPC package reader, EASA Parser, Canonical Regulation AST, Markdown Renderer, CLI (`inspect`, `convert`).
- Milestone 2: Inline formatting, lists, hyperlinks scaffolding, internal reference model.
- Milestone 3: Asset extraction and image parsing.
- Milestone 4: Validation framework skeleton and conversion report.
- Milestone 6: Real validation package (`structure`, `links`, `assets`, `output`, `report`), richer `conversion-report.json`, source topic-count check, golden tests under `tests/golden/`.

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
