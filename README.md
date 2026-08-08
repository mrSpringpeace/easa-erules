# EASA eRules (`easa-erules`)

Univerzální, deterministický nástroj pro práci s EASA Easy Access Rules / eRules XML publikacemi.

## Funkce (aktuální stav)

- Načtení EASA XML / Flat OPC a OOXML (`.docx`) balíčků
- Stažení z EASA landing pages (`fetch`) + lokální cache s integrity metadata
- Konverze do kanonického `Regulation AST`
- Deterministický export do **Markdown** a **JSON**
- Extrakce jednotlivých požadavků podle označení / ERulesID
- Validace s `conversion-report.json`
- Vestavěný katalog zdrojů v `sources/easa.yaml` (`cs-vla`, `cs-lsa`, `cs-22`, `cs-23`)

### Plánováno (ještě není v MVP)

- HTML renderer
- `refs` command (reference graph)

## Instalace

```bash
pip install -e ".[dev]"
# nebo s uv:
uv venv && source .venv/bin/activate && uv pip install -e ".[dev]"
```

## Rychlé použití

```bash
easa-erules list
easa-erules info vla                    # alias funguje
easa-erules fetch cs-vla                # latest XML → ~/.cache/easa-erules/
easa-erules fetch cs-vla --version "Amendment 1"
easa-erules inspect cs-vla              # z cache
easa-erules convert cs-vla -o ./out --split
easa-erules convert ./CS-VLA.xml -o ./out --split
easa-erules extract cs-vla CS-VLA.303 --format json
easa-erules query cs-vla "factor of safety" --json
easa-erules validate ./out
```

Cache root: `~/.cache/easa-erules/` (override: `EASA_ERULES_CACHE`).  
Search index: `~/.cache/easa-erules/<doc>/search.sqlite` (auto-built on first `query`).

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

## Validace

```bash
easa-erules convert ./CS-VLA.xml -o ./out --split
easa-erules validate ./out
# conversion-report.json obsahuje počty, duplicate ERulesId, missing images,
# unresolved references a porovnání source topic count vs AST
```

## Vývoj

```bash
pytest
ruff check src tests
# Golden testy: tests/golden/<case>/{expected.md,expected.json,expected-report.json}
```

## Licence

MIT
