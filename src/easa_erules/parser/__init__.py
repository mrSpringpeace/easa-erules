"""EASA Parser package."""

from .document import EasaDocumentParser, ParseResult, parse_easa_document
from .figures import FigureParser
from .hyperlinks import HyperlinkParser
from .lists import ListParser
from .metadata import MetadataParser
from .paragraphs import ParagraphParser
from .tables import TableParser
from .topics import TopicParser

__all__ = [
    "EasaDocumentParser",
    "FigureParser",
    "HyperlinkParser",
    "ListParser",
    "MetadataParser",
    "ParagraphParser",
    "ParseResult",
    "TableParser",
    "TopicParser",
    "parse_easa_document",
]
