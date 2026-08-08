"""OOXML Relationships handling."""

from dataclasses import dataclass

from lxml import etree

from .namespaces import REL


@dataclass(frozen=True, slots=True)
class Relationship:
    """Represents a single OOXML relationship."""
    id: str
    type: str
    target: str
    target_mode: str = "Internal"

    @property
    def is_external(self) -> bool:
        return self.target_mode == "External"

    @property
    def is_internal(self) -> bool:
        return self.target_mode == "Internal"


class Relationships:
    """Collection of relationships for a package part."""

    def __init__(self, relationships: dict[str, Relationship] | None = None):
        self._rels: dict[str, Relationship] = relationships or {}

    @classmethod
    def from_xml(cls, xml_bytes: bytes) -> "Relationships":
        """Parse relationships from XML bytes."""
        root = etree.fromstring(xml_bytes)
        rels = {}
        # Attributes in OOXML relationships are in no namespace (unprefixed)
        for elem in root.findall(f".//{{{REL}}}Relationship"):
            rel_id = elem.get("Id")
            rel_type = elem.get("Type")
            target = elem.get("Target")
            target_mode = elem.get("TargetMode", "Internal")
            if rel_id and rel_type and target:
                rels[rel_id] = Relationship(rel_id, rel_type, target, target_mode)
        return cls(rels)

    def get(self, rel_id: str) -> Relationship | None:
        return self._rels.get(rel_id)

    def find_by_type(self, rel_type: str) -> list[Relationship]:
        return [r for r in self._rels.values() if r.type == rel_type]

    def find_by_target(self, target: str) -> list[Relationship]:
        return [r for r in self._rels.values() if r.target == target]

    def __iter__(self):
        return iter(self._rels.values())

    def __len__(self) -> int:
        return len(self._rels)

    def __contains__(self, rel_id: str) -> bool:
        return rel_id in self._rels


# Common relationship types
class RelTypes:
    """Standard OOXML relationship type URIs."""
    OFFICE_DOCUMENT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    STYLES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"
    NUMBERING = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering"
    SETTINGS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings"
    FONT_TABLE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable"
    FOOTNOTES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
    ENDNOTES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/endnotes"
    COMMENTS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
    IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
    HYPERLINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
    HEADER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"
    FOOTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"
    HEADER_FOOTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/headerFooter"
    CUSTOM_XML = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"
    CUSTOM_XML_PROPS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXmlProps"
    EXTENDED_PROPERTIES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties"
    CORE_PROPERTIES = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties"
    THUMBNAIL = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"