"""Canonical Regulation AST - Model package."""

from .assets import (
    Asset,
    AssetCollection,
)
from .document import (
    DocumentMetadata,
    RegulationDocumentWrapper,
    create_document,
)
from .metadata import (
    EasaMetadata,
    RequirementMetadata,
)
from .node import (
    AcceptableMeansOfComplianceNode,
    AstNode,
    BoldNode,
    FigureNode,
    GuidanceNode,
    HeadingNode,
    HyperlinkNode,
    InlineNode,
    InternalReferenceNode,
    ItalicNode,
    LineBreakNode,
    ListItemNode,
    ListNode,
    Node,
    NodeType,
    ParagraphNode,
    ReferenceNode,
    RegulationDocument,
    RegulationRequirement,
    RegulationSection,
    SubscriptNode,
    SuperscriptNode,
    TableNode,
    TextNode,
)
from .references import (
    Reference,
    ReferenceIndex,
    ReferenceType,
)

__all__ = [
    # Node types
    "Node",
    "NodeType",
    "InlineNode",
    "TextNode",
    "BoldNode",
    "ItalicNode",
    "SuperscriptNode",
    "SubscriptNode",
    "HyperlinkNode",
    "InternalReferenceNode",
    "LineBreakNode",
    "ParagraphNode",
    "HeadingNode",
    "ListNode",
    "ListItemNode",
    "TableNode",
    "FigureNode",
    "ReferenceNode",
    "RegulationDocument",
    "RegulationSection",
    "RegulationRequirement",
    "GuidanceNode",
    "AcceptableMeansOfComplianceNode",
    "AstNode",
    # Document
    "DocumentMetadata",
    "RegulationDocumentWrapper",
    "create_document",
    # Metadata
    "EasaMetadata",
    "RequirementMetadata",
    # References
    "Reference",
    "ReferenceType",
    "ReferenceIndex",
    # Assets
    "Asset",
    "AssetCollection",
]