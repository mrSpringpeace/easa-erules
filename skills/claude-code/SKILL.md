---
name: easa-erules
description: Claude Code adapter for EASA Easy Access Rules via easa-erules CLI.
---

# easa-erules (Claude Code)

Use the local `easa-erules` CLI as the only source of regulatory text.

## Do

- `easa-erules list|info|fetch|query|extract|refs|convert|validate`
- Pass `--json` for structured tool results
- Keep regulatory quotes verbatim from tool output

## Do not

- Reconstruct rules from memory
- Implement XML parsing in the agent
- Skip validation after bulk `convert`

Workflow details: `skills/generic/SKILL.md`.
