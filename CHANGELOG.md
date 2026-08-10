# Changelog

All notable changes to this project will be documented in this file.

## [0.2.1] - 2026-08-10

Follow-up to 0.2.0, working through the four escalated decisions. The catalog
was verified end to end for the first time, which surfaced two more defects.

### Fixed

- **The resolver silently substituted the wrong format.** When a landing page
  offered no XML, `select_publication` fell back to any publication and handed
  back a PDF labelled as the XML export. `cs-p` and `cs-etso` failed several
  layers down with "Downloaded content is not XML or ZIP". Now it raises with
  the formats that are actually available, and both entries are marked
  `xml_available: false` so commands explain themselves instead.
- **`catalog_health.py` reported those entries as green** because it only
  checked that *a* publication was selected. It now verifies the format and,
  with `--deep`, downloads and parses every entry.
- **The catalog's `preferred_format` never took effect** — a hardcoded `"xml"`
  default in `resolve()` always won over the YAML value.
- **Repeated ERulesIds were treated as corruption.** An AMC or GM covering
  several rules is printed once under each of them with the same id; Part-21
  has 25 such items across 67 occurrences. Validation now separates
  `repeated_erules_ids` (identical designation, title and body — a warning)
  from `duplicate_erules_ids` (differing content — an error). Part-21 and
  `uas-rules` validate cleanly.
- **The FAA adapter never resolved references.** Reference resolution moved to
  a shared `resolve_document_references`, used by both authorities. It also
  counted subpart containers as AST topics but not as source topics, producing
  a false `topic_count_mismatch` on every part.

### Added

- **`NOTICE`** bounding the MIT grant: it covers the software only, not
  regulatory text. Records EASA's attribution requirement and 14 CFR's public
  domain status.
- **FAR citation detection** — `§ 25.1309`, `§§ 25.1309, 25.1322 and 25.1353`,
  `14 CFR 23.2005(a)`, including the tail of a citation list. 14 CFR 25 goes
  from 0 to 695 detected references, 660 of them resolved.
- **The FAA adapter now reports what it cannot model.** Each flattened table
  produces a `table_flattened` warning with section, row and cell counts; each
  image is recorded as an unknown element. On 14 CFR 25 that is 32 tables and
  88 images, all visible in `conversion-report.json`. The "no silent content
  loss" rule now holds on the experimental branch too.
- **`extract` reports `occurrences`** and warns `repeated_in_source` when the
  publisher prints an item more than once, instead of silently returning the
  first of seven.
- `catalog_health.py --deep` and `--only`; the weekly workflow runs deep.

### Changed

- **The FAA branch is labelled experimental** throughout. EASA remains the
  maintained branch, and the package keeps the name `easa-erules` — see
  `docs/STATUS.md` for the reasoning.
- **Git history is not being rewritten.** EASA's copyright policy authorises
  reproduction with acknowledgement, and the "Official Publication" clause that
  prompted the concern is a disclaimer, not a copyright carve-out. Publications
  stay out of the repository on engineering grounds. See `docs/LEGAL-REVIEW.md`.
- Validation reports carry `repeated_erules_ids`; the duplicate error type is
  now `conflicting_erules_id`.

## [0.2.0] - 2026-08-10

Agent-facing release. The JSON shape changed — see **Breaking** below.

### Fixed

- **`query` crashed on CS-VLA.** Sections sharing a title (CS-VLA has five
  `GENERAL` sections) were assigned the same node id, which violated the unique
  constraint on the FTS index. Deterministic ids are now deduplicated within a
  document.
- **Broken image and rule links for parenthesised designations.** `AMC VLA
  613(c)` produced `![](assets/amc-vla-613(c).png)`, which truncates at the
  first `(`. Markdown link destinations are percent-encoded; the validator
  decodes before checking the path.
- **`--json` output was not always parseable.** `rich` soft-wrapped long values,
  so piping into `jq` could fail. Machine-readable output now goes to stdout as
  plain JSON.

### Breaking

- Every machine-readable output is wrapped in a versioned envelope:
  `schema_version`, `status`, `source`, `warnings`, then the command payload.
  `extract` results moved under `rule`, `refs` under `refs`, `fetch` under
  `fetch`. `schema_version` is `1.0` and is versioned independently of the
  package.
- Commands exit with a status-specific code: `ok`/`no_match` 0, `not_cached` 3,
  `index_missing` 4, `fetch_failed` 5, `source_drift` 6, `parse_error` 7,
  `error` 1.
- Real EASA publications are no longer committed to the repository. Fetch them
  with `python tests/real_samples/fetch_samples.py`; tests marked `real_sample`
  skip when they are absent. See `docs/LEGAL-REVIEW.md`.
- The ASTM adapter stub was removed. Those standards are paywalled and cannot be
  redistributed, so the extension point promised something that was never coming.

### Added

- **Provenance in every output.** A `source` block naming the regulation, issue,
  amendment, sha256, retrieval time and download URL. Issue and amendment fail
  fast to `unknown` with a warning rather than a silent `null`. The same block
  appears in Markdown frontmatter, `metadata.yaml` and `conversion-report.json`.
- **Cross-references detected in running text.** Official EAR packages rarely
  mark citations up as elements, so the reference graph was near-empty on real
  documents. A normalization pass now finds designations in text — including
  ones Word split across runs — and sub-paragraph citations resolve to their
  parent rule.
- **MCP server** (`easa-erules-mcp`, optional `[mcp]` extra) exposing
  `list_regulations`, `regulation_info`, `extract_rule`, `query_regulation`,
  `rule_references` and `fetch_regulation` over stdio.
- **FAA adapter** for 14 CFR via the public eCFR API, with six catalogued parts
  (`far-21`, `far-23`, `far-25`, `far-27`, `far-43`, `far-91`). Produces the same
  AST, so `extract` / `query` / `refs` work unchanged.
- **`easa_erules.api`** — front-end-independent operations shared by the CLI and
  the MCP server, so both return identical results.
- **Scope guardrail** in all four skill adapters: this is an EASA source and is
  not a substitute for the FAA certification basis; `no_match` is not evidence
  that a requirement does not exist.
- **Catalog health workflow** (`catalog-health.yml` + `scripts/catalog_health.py`)
  probing all 18 entries weekly and reporting drift as an artifact, without
  failing the build.
- `docs/STATUS.md` (moved out of the README) and `docs/LEGAL-REVIEW.md`.

## [0.1.2] - 2026-08-09

### Fixed
- Packaging: require setuptools≥77; resolve `project.license-files` vs `tool.setuptools.license-files` conflict that broke CI install and PyPI build on the v0.1.1 tag.

## [0.1.1] - 2026-08-09

### Added
- **Designation quality:** robust extract/normalize for `CS-VLA.1`, `CS 23.2000` → `CS-23.2000`, `AMC VLA 21(c)`, `AMC1 23.2000` → `AMC1 CS-23.2000`, GM variants; first-line / export-title based (no full-body false positives).
- **Real-doc metadata:** parse official `erules-export` customXml (topics by `sdt-id`, `ERulesId`, TypeOfContent, RegulatorySource, ParentIR, …) plus `docProps/core.xml` / app properties.
- **CI:** `.github/workflows/ci.yml` (pytest + ruff); `.github/workflows/live-smoke.yml` (manual/weekly `cs-vla` + `cs-25` network smoke).
- **Docs:** `examples/agent-cookbook.md`, `docs/MANUAL.md` (full user/agent manual).
- **Adapters scaffold:** `easa_erules.adapters` with production EASA adapter and FAA/ASTM stubs.
- **PyPI packaging:** project classifiers/URLs, `MANIFEST.in`, publish workflow (Trusted Publishing), README badges, `docs/PUBLISHING.md`.
- Tests: `test_designation.py`, `test_export_metadata.py`; live parametrized smokes for `cs-vla` / `cs-25`.

### Fixed
- Duplicate `erules_id` noise on real CS-VLA/CS-23 (unique export ERulesIds; designations no longer collapse to bare `CS-VLA` / `CS-23`).
- Parenthetical AMC designations (`AMC VLA 21(c)` vs truncated `AMC VLA 21`).
- Corrupted MIT license warranty clause (GitHub SPDX recognition).

### Changed
- Drop unused direct `pydantic` dependency (leaner install).

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
