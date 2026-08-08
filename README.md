# EASA eRules (`easa-erules`)

Univerzální, deterministický nástroj pro práci s EASA Easy Access Rules / eRules XML publikacemi.

## Funkce (aktuální stav)

- Načtení EASA XML / Flat OPC a OOXML (`.docx`) balíčků
- Konverze do kanonického `Regulation AST`
- Deterministický export do **Markdown** a **JSON**
- Extrakce jednotlivých požadavků podle označení / ERulesID
- Validace s `conversion-report.json` (základ)
- Vestavěný katalog zdrojů (`cs-vla`, `cs-lsa`, `cs-22`, `cs-23`)

### Plánováno (ještě není v MVP)

- `fetch` / source resolver (stažení z EASA landing pages)
- Lokální vyhledávání (SQLite FTS5)
- HTML renderer
- Cache `~/.cache/easa-erules/`

## Instalace

```bash
pip install -e ".[dev]"
# nebo s uv:
uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
```

## Rychlé použití

```bash
easa-erules list
easa-erules info vla          # alias funguje
easa-erules inspect ./CS-VLA.xml
easa-erules convert ./CS-VLA.xml -o ./out --split
easa-erules extract ./CS-VLA.xml CS-VLA.303 --format json
easa-erules validate ./out
```

### Výstup `convert --split -o ./out`

```text
out/
├── index.md
├── metadata.yaml
├── document.json
├── conversion-report.json
├── rules/
│   └── cs-vla-303.md
└── assets/
    └── cs-vla-303-fig-01.png
```

## Vývoj

```bash
pytest
ruff check src tests
```

## Licence

MIT
