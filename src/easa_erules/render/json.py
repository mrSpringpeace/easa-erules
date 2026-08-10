"""JSON renderer for Regulation AST."""

from typing import Any

from ..contract import SCHEMA_VERSION
from ..model import (
    AcceptableMeansOfComplianceNode,
    AssetCollection,
    BoldNode,
    FigureNode,
    GuidanceNode,
    HeadingNode,
    HyperlinkNode,
    InternalReferenceNode,
    ItalicNode,
    ListItemNode,
    ListNode,
    Node,
    ParagraphNode,
    ReferenceIndex,
    ReferenceNode,
    RegulationDocument,
    RegulationRequirement,
    RegulationSection,
    SubscriptNode,
    SuperscriptNode,
    TableNode,
    TextNode,
)


class JSONRenderer:
    """Renderer for converting Regulation AST to JSON."""

    def __init__(
        self,
        include_assets: bool = True,
        include_references: bool = True,
        provenance: dict[str, Any] | None = None,
    ):
        self.include_assets = include_assets
        self.include_references = include_references
        self.provenance = provenance

    def render(self, doc: RegulationDocument, assets: AssetCollection | None = None,
               references: ReferenceIndex | None = None) -> dict[str, Any]:
        """Render document to JSON-serializable dict."""
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "document": self._render_node(doc),
        }
        if self.provenance is not None:
            result["source"] = self.provenance

        if self.include_assets and assets:
            result["assets"] = assets.to_dict()

        if self.include_references and references:
            result["references"] = references.to_dict()

        return result

    def render_requirement(self, req: RegulationRequirement) -> dict[str, Any]:
        """Render a single requirement to JSON."""
        return self._render_node(req)

    def _render_node(self, node: Node) -> dict[str, Any]:
        """Recursively render node to dict."""
        base = {
            "type": node.type.value,
            "id": node.id,
            "metadata": node.metadata,
        }

        # Add type-specific fields
        if isinstance(node, RegulationDocument):
            base.update({
                "title": node.title,
                "authority": node.authority,
                "version": node.version,
                "document_id": node.document_id,
                "easa_metadata": node.easa_metadata,
            })
        elif isinstance(node, RegulationSection):
            base.update({
                "designation": node.designation,
                "title": node.title,
                "level": node.level,
            })
        elif isinstance(node, RegulationRequirement):
            base.update({
                "designation": node.designation,
                "title": node.title,
                "erules_id": node.erules_id,
                "requirement_type": node.requirement_type,
            })
        elif isinstance(node, GuidanceNode) or isinstance(node, AcceptableMeansOfComplianceNode):
            base.update({
                "designation": node.designation,
                "title": node.title,
                "erules_id": node.erules_id,
            })
        elif isinstance(node, HeadingNode):
            base.update({
                "level": node.level,
                "designation": node.designation,
            })
        elif isinstance(node, ParagraphNode):
            base["text"] = node.get_text()
        elif isinstance(node, ListNode):
            base.update({
                "ordered": node.ordered,
                "start_number": node.start_number,
            })
        elif isinstance(node, ListItemNode):
            base["number"] = node.number
        elif isinstance(node, TableNode):
            base.update({
                "caption": node.caption,
                "headers": self._render_table_content(node.headers),
                "rows": self._render_table_content(node.rows),
            })
        elif isinstance(node, FigureNode):
            base.update({
                "image_path": node.image_path,
                "caption": node.caption,
                "alt_text": node.alt_text,
            })
        elif isinstance(node, ReferenceNode):
            base.update({
                "target_id": node.target_id,
                "target_designation": node.target_designation,
                "ref_type": node.ref_type,
            })
        elif isinstance(node, (TextNode, BoldNode, ItalicNode, SuperscriptNode, SubscriptNode)):
            base["text"] = node.text
        elif isinstance(node, HyperlinkNode):
            base.update({
                "text": node.text,
                "url": node.url,
            })
        elif isinstance(node, InternalReferenceNode):
            base.update({
                "text": node.text,
                "target_id": node.target_id,
                "target_designation": node.target_designation,
            })

        # Render children
        if node.children:
            base["children"] = [self._render_node(child) for child in node.children]

        return base

    def _render_table_content(self, rows: list[list[Any]]) -> list[list[Any]]:
        """Render table rows."""
        result = []
        for row in rows:
            rendered_row = []
            for cell in row:
                if isinstance(cell, list):
                    rendered_cell = [self._render_node(item) for item in cell]
                else:
                    rendered_cell = self._render_node(cell)
                rendered_row.append(rendered_cell)
            result.append(rendered_row)
        return result


def render_json(
    doc: RegulationDocument | Node,
    assets: AssetCollection | None = None,
    references: ReferenceIndex | None = None,
    include_assets: bool = True,
    include_references: bool = True,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convenience function to render document or a single node to JSON."""
    renderer = JSONRenderer(
        include_assets=include_assets,
        include_references=include_references,
        provenance=provenance,
    )
    if isinstance(doc, RegulationDocument):
        return renderer.render(doc, assets, references)
    # Single-rule / node extract shape preferred by agent workflows
    if isinstance(doc, RegulationRequirement):
        return {
            "id": doc.erules_id or doc.id,
            "rule": doc.designation,
            "title": doc.title,
            "metadata": doc.metadata,
            "content": [renderer._render_node(child) for child in doc.children],
            "references": [],
        }
    return renderer._render_node(doc)
