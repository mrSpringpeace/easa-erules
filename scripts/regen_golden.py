#!/usr/bin/env python3
"""Regenerate the frozen golden artifacts from the current parser and renderers.

Run this only when a rendering change is intended, then read the diff — the
goldens are the regression net, so regenerating without reading them throws the
net away.

    python scripts/regen_golden.py
    git diff tests/golden
"""
import json
import shutil
from pathlib import Path

from easa_erules.input.package import OpcPackage
from easa_erules.parser import EasaDocumentParser
from easa_erules.render import render_json, render_markdown
from easa_erules.validation import validate_document

root = Path("tests/golden")
for case_dir in sorted(p for p in root.iterdir() if p.is_dir()):
    meta = json.loads((case_dir / "case.json").read_text())
    result = EasaDocumentParser(OpcPackage.from_file(meta["fixture"])).parse()
    files = render_markdown(result.document, split_by_rule=bool(meta.get("split")))

    if meta.get("split"):
        expected_root = case_dir / "expected"
        if expected_root.exists():
            shutil.rmtree(expected_root)
        for name, content in files.items():
            target = expected_root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    else:
        (case_dir / "expected.md").write_text(next(iter(files.values())), encoding="utf-8")

    doc_json = render_json(result.document, result.assets, result.references)
    (case_dir / "expected.json").write_text(
        json.dumps(doc_json, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    report = validate_document(
        result.document,
        result.assets,
        result.references,
        parse_warnings=result.warnings,
        unknown_elements=result.unknown_elements,
        source_topic_count=result.source_topic_count,
    )
    (case_dir / "expected-report.json").write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("regenerated", case_dir.name)
