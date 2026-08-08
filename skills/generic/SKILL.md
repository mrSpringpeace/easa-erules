---
name: easa-erules
description: Work with EASA Easy Access Rules via the easa-erules CLI (deterministic parse/convert/query).
---

# easa-erules skill (generic)

Use **easa-erules** whenever a task needs authoritative EASA Easy Access Rules content.

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

## Examples

```bash
easa-erules fetch cs-vla
easa-erules query cs-vla "design airspeeds" --json
easa-erules extract cs-vla CS-VLA.303 --format json
easa-erules refs cs-vla CS-VLA.303 --json
```
