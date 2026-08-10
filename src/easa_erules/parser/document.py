"""EASA document parser - main entry point."""

import re
from dataclasses import dataclass
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

#: Trailing sub-paragraph markers on a citation, e.g. ``(a)(1)`` in ``CS-23.2240(a)(1)``.
_SUBPARAGRAPH_SUFFIX = re.compile(r"(\([a-z0-9]+\))+$", re.IGNORECASE)


def base_designation(designation: str) -> str:
    """Strip sub-paragraph markers from a citation.

    ``CS-23.2240(a)`` → ``CS-23.2240``. Running text cites sub-paragraphs, but
    only the rule itself is a topic, so resolution needs the base form.
    Returns an empty string when there is nothing to strip.
    """
    stripped = _SUBPARAGRAPH_SUFFIX.sub("", designation or "").strip()
    return stripped if stripped and stripped != designation else ""


@dataclass
class ParseResult:
    """Result of parsing an EASA document."""
    document: RegulationDocument
    assets: AssetCollection
    references: ReferenceIndex
    warnings: list[dict[str, Any]]
    unknown_elements: list[dict[str, Any]]
    source_topic_count: int = 0


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
        self.unknown_elements: list[dict[str, Any]] = []
        self.source_topic_count = 0
        self._element_handlers: dict[str, callable] = {}

    def parse(self) -> ParseResult:
        """Parse the entire document into a RegulationDocument AST."""
        if not self.doc_part:
            raise ValueError("No main document part found in package")

        # Create root document
        self.document = RegulationDocument()
        self.document.metadata = {}

        # Parse numbering definitions for list formatting
        self.list_parser.parse_numbering_definitions()

        root_xml = self.doc_part.xml()

        # Count source topics before parse (content-loss baseline)
        from ..input.namespaces import ERULES, ERULES_EXPORT, W
        topic_elems = root_xml.findall(f".//{{{ERULES}}}topic")
        topic_elems += root_xml.findall(f".//{{{ERULES_EXPORT}}}topic")
        # Real EAR packages: topics/headings as Word SDT alias/tag values
        sdt_topics = 0
        for sdt in root_xml.findall(f".//{{{W}}}sdt"):
            if self._sdt_kind(sdt) in ("topic", "heading"):
                sdt_topics += 1
        self.source_topic_count = len(topic_elems) + sdt_topics

        # Parse document metadata first
        self.metadata_parser.parse(root_xml)

        # Parse document body
        body = root_xml.find(f".//{{{W}}}body")
        if body is not None:
            self._parse_body(body)

        # Deterministic IDs before reference resolution (refs link by id)
        from ..util.ids import assign_deterministic_ids
        assign_deterministic_ids(self.document)

        # Normalize AST (whitespace, headings, list numbers, ref designations)
        from ..normalize import normalize_document
        normalize_document(self.document)

        # Post-process: resolve references and update inline nodes
        self._resolve_references()

        return ParseResult(
            document=self.document,
            assets=self.assets,
            references=self.references,
            warnings=self.warnings,
            unknown_elements=self.unknown_elements,
            source_topic_count=self.source_topic_count,
        )

    def _parse_body(self, body: etree._Element) -> None:
        """Parse the document body element by element."""
        for child in body:
            self._parse_element(child, self.document)

    def _parse_element(self, elem: etree._Element, parent: Any) -> None:
        """Dispatch element to appropriate parser."""
        from ..input.namespaces import ERULES_NAMESPACES, W

        if not isinstance(elem.tag, str):
            return

        tag = etree.QName(elem.tag).localname
        ns = etree.QName(elem.tag).namespace or ""

        # Handle EASA custom elements (fixture + official export namespaces)
        if ns in ERULES_NAMESPACES:
            self._parse_erules_element(elem, parent)
            return

        # Real EAR packages: structured document tags for topics/headings
        if tag == "sdt" and ns == W:
            self._parse_sdt(elem, parent)
            return

        # Standard WordprocessingML elements
        handler = self._element_handlers.get(tag)
        if handler:
            handler(elem, parent)
        else:
            if tag == "p":
                self.paragraph_parser.parse(elem, parent)
            elif tag == "tbl":
                self.table_parser.parse(elem, parent)
            elif tag in ("sectPr", "bookmarkStart", "bookmarkEnd", "proofErr"):
                return  # structural noise
            else:
                self._add_warning(f"Unhandled element: {tag}", elem)

    def _sdt_kind(self, sdt: etree._Element) -> str | None:
        """Return 'topic' / 'heading' / other from SDT alias or tag."""
        from ..input.namespaces import W, qname

        for local in ("alias", "tag"):
            el = sdt.find(f".//{qname(W, local)}")
            if el is not None:
                val = (el.get(qname(W, "val")) or "").strip().lower()
                if val in ("topic", "heading"):
                    return val
        return None

    def _parse_sdt(self, elem: etree._Element, parent: Any) -> None:
        """Parse a Word structured document tag (real EASA EAR packaging)."""
        from ..input.namespaces import W, qname

        kind = self._sdt_kind(elem)
        content = elem.find(qname(W, "sdtContent"))
        if content is None:
            content = elem.find(f".//{qname(W, 'sdtContent')}")

        if kind == "topic":
            self.topic_parser.parse_sdt(elem, content, parent)
            return
        if kind == "heading":
            # Treat structural headings as section-like nodes from first para
            if content is not None:
                self.topic_parser.parse_sdt_heading(content, parent)
            return

        # Unknown SDT — still parse content so text is not lost
        if content is not None:
            for child in content:
                self._parse_element(child, parent)

    def _parse_erules_element(self, elem: etree._Element, parent: Any) -> None:
        """Parse EASA custom XML elements."""
        local = etree.QName(elem.tag).localname

        if local == "topic":
            self.topic_parser.parse(elem, parent)
        elif local == "metadata":
            # Already parsed at document level, but could be nested
            self.metadata_parser.parse_nested(elem, parent)
        else:
            self._add_unknown_element(f"Unknown EASA element: {local}", elem)

    def _add_warning(self, message: str, elem: etree._Element | None = None) -> None:
        warning = {"message": message}
        if elem is not None:
            warning["element"] = etree.QName(elem.tag).localname
            warning["xpath"] = self._get_xpath(elem)
        self.warnings.append(warning)

    def _add_unknown_element(self, message: str, elem: etree._Element | None = None) -> None:
        warning = {"message": message}
        if elem is not None:
            warning["element"] = etree.QName(elem.tag).localname
            warning["xpath"] = self._get_xpath(elem)
        self.unknown_elements.append(warning)

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
        from ..model import InternalReferenceNode

        # Build designation -> node index
        by_designation: dict[str, Any] = {}
        self._index_designations(self.document, by_designation)

        def normalize(des: str) -> str:
            return des.replace(" ", "-").upper()

        norm_index = {normalize(k): v for k, v in by_designation.items()}

        def find_target(designation: str) -> Any | None:
            """Exact match, else fall back to the parent rule of a sub-paragraph.

            Running text cites ``CS-23.2240(a)``; only ``CS-23.2240`` is a topic.
            Resolving to the parent keeps the sub-paragraph in the designation
            while still producing a usable edge.
            """
            node = by_designation.get(designation) or norm_index.get(normalize(designation))
            if node is not None:
                return node
            base = base_designation(designation)
            if base:
                return by_designation.get(base) or norm_index.get(normalize(base))
            return None

        for ref in self.references.by_designation.values():
            if ref.target_designation and not ref.resolved:
                target_node = find_target(ref.target_designation)
                if target_node:
                    ref.target_id = target_node.id
                    ref.resolved = True
                    if ref.target_id:
                        self.references.by_target.setdefault(ref.target_id, []).append(ref)

        # Update inline InternalReferenceNode instances
        def walk(node: Any) -> None:
            if isinstance(node, InternalReferenceNode) and node.target_designation:
                target_node = find_target(node.target_designation)
                if target_node:
                    node.target_id = target_node.id
            for child in getattr(node, "children", []):
                walk(child)

        walk(self.document)

    def _index_designations(self, node: Any, index: dict[str, Any]) -> None:
        if hasattr(node, "designation") and node.designation:
            index.setdefault(node.designation, node)
        if hasattr(node, "erules_id") and node.erules_id:
            index.setdefault(node.erules_id, node)
        for child in getattr(node, "children", []):
            self._index_designations(child, index)

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
    result = parser.parse()
    return result.document