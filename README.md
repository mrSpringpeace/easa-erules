# EASA eRules (`easa-erules`)

Univerzální, deterministický nástroj pro práci s EASA Easy Access Rules / eRules XML publikacemi.

## Funkce
- Načtení EASA XML / Flat OPC publikací
- Konverze do kanonického `Regulation AST`
- Deterministický export do Markdown, JSON, HTML
- Extrakce jednotlivých požadavků podle pravidla / ERulesID
- Lokální vyhledávání (SQLite / FTS5)
- Validace bez ztráty obsahu (conversion report)

## Instalace
```bash
pip install -e .
```

## Rychlé použití
```bash
easa-erules list
easa-erules convert ./CS-VLA.xml
easa-erules inspect ./CS-VLA.xml
```
