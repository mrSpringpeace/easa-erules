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

## 9. Multi-authority adapters (future)

```python
from easa_erules.adapters import get_adapter

easa = get_adapter("easa")
result = easa.parse("tests/real_samples/cs-vla.xml")

# Scaffolds — raise NotImplementedError on fetch/parse:
# get_adapter("faa"), get_adapter("astm")
```

See `src/easa_erules/adapters/README.md`.
