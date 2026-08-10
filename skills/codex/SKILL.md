---
name: easa-erules
description: Codex adapter for EASA Easy Access Rules via easa-erules CLI.
---

# easa-erules (Codex)

Thin adapter — do not reimplement the parser.

When the user asks about EASA CS / Easy Access Rules / certification specifications:

1. Run CLI commands with `easa-erules` (install: `pip install -e .` in the project if needed).
2. Prefer `query` / `extract` / `refs` with `--json` over dumping entire regulations into context.
3. Never hand-write regulatory paragraphs; always ground answers in CLI output.
4. If the source is missing: `easa-erules fetch <doc-id>` first.

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

## Reading the output

Every JSON result carries `schema_version`, `status`, `source` and `warnings`.
Exit codes: `ok`/`no_match` 0, `not_cached` 3, `index_missing` 4, `fetch_failed` 5,
`source_drift` 6, `parse_error` 7, `error` 1.

**`no_match` is not evidence that a requirement does not exist** — it means this
document, at this amendment, with these terms, returned nothing. Confirm the
regulation and amendment before telling a user a rule is absent.

Full status table and workflow: `skills/generic/SKILL.md`.
