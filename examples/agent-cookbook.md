# Agent cookbook — end-to-end `easa-erules` workflows

Short recipes for LLM agents and humans. Prefer **JSON** outputs. Never invent regulatory text.

For full CLI and architecture details see [`docs/MANUAL.md`](../docs/MANUAL.md).

## 0. Install once

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
# or: pip install -e ".[dev]"
```

## 1. Discover and fetch

```bash
easa-erules list
easa-erules info cs-vla
easa-erules fetch cs-vla
easa-erules fetch cs-vla --version "Amendment 1"
```

Use registry **id** or **alias** (`vla`, `csvla`, `CS23`, …). Cache lives under `~/.cache/easa-erules/` (override with `EASA_ERULES_CACHE`).

## 2. Answer a factual question about a known rule

```bash
easa-erules extract cs-vla CS-VLA.1 --format json
easa-erules extract cs-vla CS-VLA.303 --format json
easa-erules extract cs-23 CS-23.2000 --format json
```

Designations on real EAR packages look like:

| Kind | Examples |
|------|----------|
| CS (letter code) | `CS-VLA.1`, `CS-VLA.303` |
| CS (numeric part) | `CS-23.2000`, `CS-23.2100` |
| AMC | `AMC VLA 1`, `AMC VLA 21(c)`, `AMC1 CS-23.2000` |
| GM | `GM1 CS-23.2010` |

## 3. Search when the rule id is unknown

```bash
easa-erules query cs-vla "factor of safety" --json
easa-erules query cs-23 "stall speed" --json
easa-erules query cs-vla "centre of gravity" --json --rebuild
```

SQLite FTS5 index is built on first query and invalidated when the source SHA or parser version changes.

## 4. Follow cross-references

```bash
easa-erules refs cs-vla CS-VLA.303 --json
easa-erules refs cs-23 CS-23.2010 --json
```

Use outgoing refs to pull related AMC/GM, then `extract` each target.

## 5. Bulk convert for offline reading

```bash
easa-erules convert cs-vla -o ./out/cs-vla --split
easa-erules convert cs-23 -o ./out/cs-23 --format html
easa-erules validate ./out/cs-vla
```

Split layout:

```text
out/cs-vla/
├── index.md
├── metadata.yaml
├── document.json
├── conversion-report.json
├── rules/
│   └── …
└── assets/
```

## 6. Inspect before trusting a new package

```bash
easa-erules inspect cs-vla
easa-erules inspect ./local-export.xml
```

Check topic counts, warnings, and unknown elements. Real packages should show **zero duplicate ERulesIds** after designation/metadata polish.

## 6b. Read the envelope before reading the payload

Every `--json` result starts with the same four fields:

```bash
easa-erules extract cs-vla CS-VLA.303 --format json | jq '{status, amendment: .source.amendment, warnings}'
```

```json
{"status": "ok", "amendment": "Amendment 1", "warnings": []}
```

Branch on `status`, not on whether the payload looks empty:

```bash
easa-erules query cs-vla "zero lift drag" --json > out.json
case "$(jq -r .status out.json)" in
  ok)          jq -r '.hits[].designation' out.json ;;
  no_match)    echo "nothing matched — check the regulation and amendment first" ;;
  not_cached)  easa-erules fetch cs-vla ;;
esac
```

Exit codes carry the same information for shell-driven agents: `ok`/`no_match` 0,
`not_cached` 3, `index_missing` 4, `fetch_failed` 5, `source_drift` 6,
`parse_error` 7, `error` 1.

**`no_match` is not proof of absence.** It means this document, at this
amendment, with these terms, returned nothing.

Never quote a requirement without `source.designation` and `source.amendment`.
If `warnings` contains `amendment_not_determined`, say that the provenance is
incomplete rather than presenting the quote as pinned.

## 7. Typical agent loop

```text
list / info → fetch (if needed) → query → extract → refs → (optional convert+validate)
```

Rules of engagement:

1. Ground answers only on tool output.
2. Prefer `query` / `extract` / `refs` with `--json` over stuffing full regulations into context.
3. After bulk `convert`, run `validate`.
4. If designation lookup fails, re-query with a shorter phrase or list nearby hits.

## 8. Live / large-package smoke (optional)

```bash
EASA_ERULES_LIVE=1 pytest tests/test_real_samples.py -k live -v
# or manually:
easa-erules fetch cs-25
easa-erules inspect cs-25
```

GitHub Actions: workflow **Live EASA smoke** (manual dispatch or weekly).

## 9. FAA parts (14 CFR) — experimental

Same commands, different authority — the AST is shared. This branch is a
prototype; its shape may change between releases:

```bash
easa-erules fetch far-23
easa-erules extract far-23 "14 CFR 23.2005" --format json
easa-erules query far-23 "stall speed" --json
```

FAA versions are eCFR issue dates, not amendment numbers:

```bash
easa-erules fetch far-23 --version 2026-08-05
```

Cross-references work here too — `refs far-25 "14 CFR 25.1309"` follows `§`
citations found in the text.

**Fidelity.** Tables are flattened to text and images are skipped. Both are
reported in `conversion-report.json` (`table_flattened` warnings, `img` unknown
elements), so check it before trusting anything structural from 14 CFR 25/27/29.

**Scope.** This is a mirror of eCFR regulation text. It carries no Advisory
Circulars, policy or preamble, and it is not a substitute for the applicable
FAA certification basis. Never answer an FAA question with CS material without
saying explicitly that it is comparative.

## 10. Over MCP instead of the shell

```bash
pip install "easa-erules[mcp]"
easa-erules-mcp        # stdio transport
```

Tools: `list_regulations`, `regulation_info`, `extract_rule`,
`query_regulation`, `rule_references`, `fetch_regulation`. They return the same
envelopes as the CLI, including `status` and `source` — a typed failure comes
back as a payload, not a transport error.
