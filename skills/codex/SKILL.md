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

See also `skills/generic/SKILL.md` for the full workflow.
