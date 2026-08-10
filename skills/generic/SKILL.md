---
name: easa-erules
description: Work with EASA Easy Access Rules via the easa-erules CLI (deterministic parse/convert/query).
---

# easa-erules skill (generic)

Use **easa-erules** whenever a task needs authoritative EASA Easy Access Rules content.

## Scope and applicability

- This tool provides **EASA** requirements only: Certification Specifications (CS-*),
  AMC and GM, and the EU regulations in its catalog.
- It is **not** a source for the FAA certification basis. 14 CFR Part 23, the
  forthcoming Part 22 / MOSAIC rules, and FAA Advisory Circulars are not in scope
  and must never be answered from this tool.
- A CS requirement may be offered as **comparative or supplementary** material in
  an FAA context, but the answer must say so explicitly. Do not let convenient
  local access to CS text silently substitute for the applicable FAA rule.
- Never state a CS requirement without its `designation` and the `amendment` from
  the `source` block of the tool output.

## Rules

- Do **not** manually rewrite or reconstruct regulatory text.
- Prefer **JSON** output for agent workflows (`--json` / `--format json`).
- Conversion is deterministic; use the tool for text, then interpret.

## Workflow

1. Identify the regulation (`cs-vla`, `cs-23`, …) — `easa-erules list` / `info`.
2. If not available locally: `easa-erules fetch <id>`.
3. Known rule id: `easa-erules extract <id> <RULE> --format json`.
4. Subject search: `easa-erules query <id> "<terms>" --json`.
5. Cross-refs: `easa-erules refs <id> <RULE> --json`.
6. Full local tree only when needed: `easa-erules convert <id> -o ./out --split`.
7. After full convert: `easa-erules validate ./out`.
8. Base interpretation only on returned source content.

## Reading the output

Every JSON result carries `schema_version`, `status`, `source` and `warnings`.

| `status` | exit | What it means |
|----------|------|---------------|
| `ok` | 0 | Succeeded, results present |
| `no_match` | 0 | Searched, nothing matched |
| `not_cached` | 3 | Regulation not downloaded — run `fetch` or pass `--fetch` |
| `index_missing` | 4 | Search index missing or invalidated — retry with `--rebuild` |
| `fetch_failed` | 5 | Download failed |
| `source_drift` | 6 | EASA landing page no longer matches the catalog entry |
| `parse_error` | 7 | Source could not be parsed |
| `error` | 1 | Everything else (unknown id, bad path) |

**`no_match` is not evidence that a requirement does not exist.** It means this
document, at this amendment, with these search terms, returned nothing. Before
telling a user that a rule is absent, confirm the regulation and amendment are
the ones that apply, and try different terms.

Treat `warnings` as load-bearing: `issue_not_determined` or
`amendment_not_determined` means the provenance of the text you are about to
quote is incomplete. Say so rather than presenting it as pinned.

## Examples

```bash
easa-erules fetch cs-vla
easa-erules query cs-vla "design airspeeds" --json
easa-erules extract cs-vla CS-VLA.303 --format json
easa-erules refs cs-vla CS-VLA.303 --json
```
