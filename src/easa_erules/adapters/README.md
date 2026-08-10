# Authority adapters

Both adapters produce the same Regulation AST, so `extract`, `query`, `refs`,
the renderers and the search index are authority-agnostic.

| Adapter | Status | Source | Role |
|---------|--------|--------|------|
| `easa` | **Production** | EAR XML exports (Flat OPC / OOXML, Word SDT) | Full fetch / parse / search path |
| `faa` | **Prototype** | Public eCFR API, 14 CFR | Fetch / parse / search for whole parts |

```python
from easa_erules.adapters import get_adapter

easa = get_adapter("easa")
print(easa.capabilities())

faa = get_adapter("faa")
path = faa.fetch("far-23")                    # latest eCFR issue date
result = faa.parse(path)
print(result.document.title, result.source_topic_count)
```

In normal use you do not call adapters directly — `easa_erules.parsing.parse_any`
picks the right one by sniffing the file, and the CLI and MCP server go through
`easa_erules.api`.

## eCFR mapping

| eCFR | AST |
|------|-----|
| `DIV5` PART | `RegulationDocument` |
| `DIV6` SUBPART | `RegulationSection` (level 1) |
| `DIV7` SUBJGRP | `RegulationSection` (level 2) |
| `DIV8` SECTION | `RegulationRequirement`, designation `14 CFR 23.2000` |
| `P`, `FP` | `ParagraphNode` |
| `I`, `E` | `ItalicNode`, `BoldNode` |

FAA versions are eCFR **issue dates** (`--version 2026-08-05`), not amendment
numbers. With no version the adapter asks eCFR for its latest issue date — the
calendar date is not a safe default, because eCFR lags it and returns 404.

## No ASTM adapter

ASTM standards (F44 and related) are paywalled and cannot be redistributed.
There is nothing an adapter could fetch, so none exists — a stub that always
raised `NotImplementedError` only suggested the capability was coming.
