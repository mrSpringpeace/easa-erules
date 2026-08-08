---
name: easa-erules
description: OpenCode adapter for EASA Easy Access Rules via easa-erules CLI.
---

# easa-erules (OpenCode)

Call the installed `easa-erules` binary for any EASA Easy Access Rules task.

Priority order:

1. `query` — subject search (FTS5)
2. `extract` — single rule
3. `refs` — cross-reference graph
4. `convert --split` — only when a full offline tree is required
5. `validate` — after convert

Do not embed or re-author regulation text. See `skills/generic/SKILL.md`.
