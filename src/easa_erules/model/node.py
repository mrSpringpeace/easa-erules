"""Canonical Regulation AST - Core node definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union


class NodeType(str, Enum):
    """Types of nodes in the regulation AST."""
    DOCUMENT = "document"
    SECTION = "section"
    REQUIREMENT = "requirement"
    GUIDANCE = "guidance"
    AMC = "acceptable_means_of_compliance"
    GM = "guidance_material"
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST = "list"
    LIST_ITEM = "list_item"
    TABLE = "table"
    FIGURE = "figure"
    REFERENCE = "reference"
    TEXT = "text"
    BOLD = "bold"
    ITALIC = "italic"
    SUPERSCRIPT = "superscript"
    SUBSCRIPT = "subscript"
    HYPERLINK = "hyperlink"
    INTERNAL_REFERENCE = "internal_reference"
    LINE_BREAK = "line_break"


@dataclass(slots=True)
class Node:
    """Base class for all AST nodes."""
    type: NodeType = field(default=None, init=False)  # type: ignore
    # Empty by default; assign_deterministic_ids() fills stable IDs after parse.
    id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list[Node] = field(default_factory=list)
    parent: Node | None = None

    def add_child(self, child: Node) -> Node:
        child.parent = self
        self.children.append(child)
        return child

    def add_children(self, children: list[Node]) -> list[Node]:
        for child in children:
            child.parent = self
        self.children.extend(children)
        return children

    def find_children(self, node_type: NodeType) -> list[Node]:
        return [c for c in self.children if c.type == node_type]

    def find_all(self, node_type: NodeType) -> list[Node]:
        result = []
        for child in self.children:
            if child.type == node_type:
                result.append(child)
            result.extend(child.find_all(node_type))
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "id": self.id,
            "metadata": self.metadata,
            "children": [c.to_dict() for c in self.children],
        }

    def get_text(self) -> str:
        """Extract plain text from this node and its inline children."""
        return "".join(child.text for child in self.children if isinstance(child, InlineNode))


@dataclass(slots=True)
class InlineNode(Node):
    """Base for inline formatting nodes (bold, italic, etc.)."""
    text: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["text"] = self.text
        return d


@dataclass(slots=True)
class TextNode(InlineNode):
    """Plain text node."""
    text: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.TEXT


@dataclass(slots=True)
class BoldNode(InlineNode):
    """Bold text."""
    text: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.BOLD


@dataclass(slots=True)
class ItalicNode(InlineNode):
    """Italic text."""
    text: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.ITALIC


@dataclass(slots=True)
class SuperscriptNode(InlineNode):
    """Superscript text."""
    text: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.SUPERSCRIPT


@dataclass(slots=True)
class SubscriptNode(InlineNode):
    """Subscript text."""
    text: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.SUBSCRIPT


@dataclass(slots=True)
class HyperlinkNode(InlineNode):
    """External hyperlink."""
    url: str = ""
    text: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.HYPERLINK

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["url"] = self.url
        return d


@dataclass(slots=True)
class InternalReferenceNode(InlineNode):
    """Internal reference to another rule/section."""
    target_id: str = ""
    target_designation: str = ""
    text: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.INTERNAL_REFERENCE

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["target_id"] = self.target_id
        d["target_designation"] = self.target_designation
        return d


@dataclass(slots=True)
class LineBreakNode(Node):
    """Line break."""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.LINE_BREAK


# Block-level nodes
@dataclass(slots=True)
class ParagraphNode(Node):
    """Paragraph containing inline nodes."""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.PARAGRAPH

    def get_text(self) -> str:
        """Extract plain text from paragraph."""
        return "".join(child.text for child in self.children if isinstance(child, InlineNode))


@dataclass(slots=True)
class HeadingNode(Node):
    """Heading with level."""
    level: int = 1
    designation: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.HEADING


@dataclass(slots=True)
class ListNode(Node):
    """List (ordered or unordered)."""
    ordered: bool = False
    start_number: int = 1

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.LIST


@dataclass(slots=True)
class ListItemNode(Node):
    """List item."""
    number: int | None = None

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.LIST_ITEM


@dataclass(slots=True)
class TableNode(Node):
    """Table with rows and cells."""
    headers: list[list[Node]] = field(default_factory=list)
    rows: list[list[Node]] = field(default_factory=list)
    caption: str | None = None

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.TABLE


@dataclass(slots=True)
class FigureNode(Node):
    """Figure/Image with caption."""
    image_path: str = ""
    caption: str = ""
    alt_text: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.FIGURE


@dataclass(slots=True)
class ReferenceNode(Node):
    """Cross-reference."""
    target_id: str = ""
    target_designation: str = ""
    ref_type: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.REFERENCE


# Regulation-specific nodes
@dataclass(slots=True)
class RegulationDocument(Node):
    """Root document node for a regulation."""
    title: str = ""
    authority: str = ""
    version: str | None = None
    document_id: str = ""
    easa_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.DOCUMENT

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "title": self.title,
            "authority": self.authority,
            "version": self.version,
            "document_id": self.document_id,
            "easa_metadata": self.easa_metadata,
        })
        return d


@dataclass(slots=True)
class RegulationSection(Node):
    """Section within a regulation (Subpart, Chapter, etc.)."""
    designation: str = ""
    title: str = ""
    level: int = 1

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.SECTION


@dataclass(slots=True)
class RegulationRequirement(Node):
    """Individual regulatory requirement (e.g., CS-VLA.303)."""
    designation: str = ""
    title: str = ""
    erules_id: str = ""
    requirement_type: str = ""  # CS, AMC, GM, etc.
    subject_matter: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.REQUIREMENT


@dataclass(slots=True)
class GuidanceNode(Node):
    """Guidance material (GM)."""
    designation: str = ""
    title: str = ""
    erules_id: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.GUIDANCE


@dataclass(slots=True)
class AcceptableMeansOfComplianceNode(Node):
    """Acceptable Means of Compliance (AMC)."""
    designation: str = ""
    title: str = ""
    erules_id: str = ""

    def __post_init__(self):
        if not self.type:
            self.type = NodeType.AMC


# Type alias for any AST node
AstNode = Union[
    RegulationDocument,
    RegulationSection,
    RegulationRequirement,
    GuidanceNode,
    AcceptableMeansOfComplianceNode,
    ParagraphNode,
    HeadingNode,
    ListNode,
    ListItemNode,
    TableNode,
    FigureNode,
    ReferenceNode,
    TextNode,
    BoldNode,
    ItalicNode,
    SuperscriptNode,
    SubscriptNode,
    HyperlinkNode,
    InternalReferenceNode,
    LineBreakNode,
]