"""Pick the right parser for a source file.

Both authorities land in the same :class:`~easa_erules.parser.document.ParseResult`,
so everything downstream — search index, reference graph, renderers — stays
authority-agnostic and only this module needs to know the difference.
"""

from __future__ import annotations

from pathlib import Path

from .parser import ParseResult


def is_ecfr_xml(path: Path | str) -> bool:
    """True when *path* looks like an eCFR part export rather than an OOXML package."""
    try:
        with Path(path).open("rb") as fh:
            head = fh.read(512)
    except OSError:
        return False
    return b"<DIV" in head


def parse_any(path: Path | str) -> ParseResult:
    """Parse an EASA Flat OPC package or an eCFR part export."""
    path = Path(path)
    if is_ecfr_xml(path):
        from .adapters.faa import FaaEcfrAdapter

        return FaaEcfrAdapter().parse(path)

    from .input.package import OpcPackage
    from .parser import EasaDocumentParser

    return EasaDocumentParser(OpcPackage.from_file(path)).parse()
