"""EASA document parser - main entry point."""

from typing import Any

from lxml import etree

from ..input.package import OpcPackage
from ..model import (
    AssetCollection,
    ReferenceIndex,
    RegulationDocument,
)
from .figures import FigureParser
from .hyperlinks import HyperlinkParser
from .lists import ListParser
from .metadata import MetadataParser
from .paragraphs import ParagraphParser
from .tables import TableParser
from .topics import TopicParser


class EasaDocumentParser:
    """Main parser for EASA eRules documents."""

    def __init__(self, package: OpcPackage):
        self.package = package
        self.doc_part = package.get_main_document_part()
        self.styles_part = package.get_styles_part()
        self.numbering_part = package.get_numbering_part()

        # Sub-parsers
        self.metadata_parser = MetadataParser(self)
        self.topic_parser = TopicParser(self)
        self.paragraph_parser = ParagraphParser(self)
        self.table_parser = TableParser(self)
        self.figure_parser = FigureParser(self)
        self.hyperlink_parser = HyperlinkParser(self)
        self.list_parser = ListParser(self)

        # State
        self.document: RegulationDocument | None = None
        self.assets = AssetCollection()
        self.references = ReferenceIndex()
        self.warnings: list[dict[str, Any]] = []
        self._element_handlers: dict[str, callable] = {}

    def parse(self) -> RegulationDocument:
        """Parse the entire document into a RegulationDocument AST."""
        if not self.doc_part:
            raise ValueError("No main document part found in package")

        # Create root document
        self.document = RegulationDocument()
        self.document.metadata = {}

        # Parse document metadata first
        self.metadata_parser.parse(self.doc_part.xml())

        # Parse document body
        body = self.doc_part.xml().find(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}body")
        if body is not None:
            self._parse_body(body)

        # Post-process: resolve references
        self._resolve_references()

        return self.document

    def _parse_body(self, body: etree._Element) -> None:
        """Parse the document body element by element."""
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        for child in body:
            self._parse_element(child, self.document)

    def _parse_element(self, elem: etree._Element, parent: Any) -> None:
        """Dispatch element to appropriate parser."""
        tag = etree.QName(elem.tag).localname

        # Handle EASA custom elements first
        if elem.tag.startswith("{http://www.easa.europa.eu/erules}"):
            self._parse_erules_element(elem, parent)
            return

        # Standard WordprocessingML elements
        handler = self._element_handlers.get(tag)
        if handler:
            handler(elem, parent)
        else:
            # Default: try paragraph parser
            if tag == "p":
                self.paragraph_parser.parse(elem, parent)
            elif tag == "tbl":
                self.table_parser.parse(elem, parent)
            else:
                self._add_warning(f"Unhandled element: {tag}", elem)

    def _parse_erules_element(self, elem: etree._Element, parent: Any) -> None:
        """Parse EASA custom XML elements."""
        local = etree.QName(elem.tag).localname

        if local == "topic":
            self.topic_parser.parse(elem, parent)
        elif local == "metadata":
            # Already parsed at document level, but could be nested
            self.metadata_parser.parse_nested(elem, parent)
        else:
            self._add_warning(f"Unknown EASA element: {local}", elem)

    def _add_warning(self, message: str, elem: etree._Element | None = None) -> None:
        warning = {"message": message}
        if elem is not None:
            warning["element"] = etree.QName(elem.tag).localname
            warning["xpath"] = self._get_xpath(elem)
        self.warnings.append(warning)

    def _get_xpath(self, elem: etree._Element) -> str:
        """Generate XPath-like path for debugging."""
        parts = []
        while elem is not None and elem.tag != etree.Comment:
            tag = etree.QName(elem.tag).localname
            parts.append(tag)
            elem = elem.getparent()
        return "/".join(reversed(parts))

    def _resolve_references(self) -> None:
        """Resolve internal references after parsing."""
        for ref in self.references.by_designation.values():
            if ref.target_designation and not ref.target_id:
                # Try to find target by designation
                target_node = self._find_node_by_designation(self.document, ref.target_designation)
                if target_node:
                    ref.target_id = target_node.id
                    ref.resolved = True

    def _find_node_by_designation(self, node: Any, designation: str) -> Any | None:
        """Find a node by its designation (e.g., CS-VLA.303)."""
        if hasattr(node, 'designation') and node.designation == designation:
            return node
        if hasattr(node, 'erules_id') and node.erules_id == designation:
            return node
        for child in getattr(node, 'children', []):
            result = self._find_node_by_designation(child, designation)
            if result:
                return result
        return None


def parse_easa_document(package: OpcPackage) -> RegulationDocument:
    """Convenience function to parse an EASA document."""
    parser = EasaDocumentParser(package)
    return parser.parse()