"""HTML renderer for Regulation AST."""

from __future__ import annotations

import html
from io import StringIO
from typing import Any

from ..model import (
    AcceptableMeansOfComplianceNode,
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
    NodeType,
    ParagraphNode,
    RegulationDocument,
    RegulationRequirement,
    RegulationSection,
    SubscriptNode,
    SuperscriptNode,
    TableNode,
    TextNode,
)
from ..util.ids import rule_file_slug


class HTMLRenderer:
    """Renderer for converting Regulation AST to HTML."""

    def __init__(self, asset_prefix: str = "assets", title: str | None = None):
        self.asset_prefix = asset_prefix
        self.title_override = title

    def render(self, doc: RegulationDocument) -> dict[str, str]:
        """Render document to a single HTML file."""
        buf = StringIO()
        title = self.title_override or doc.title or doc.document_id or "Regulation"
        buf.write("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n")
        buf.write('  <meta charset="utf-8"/>\n')
        buf.write(f"  <title>{html.escape(title)}</title>\n")
        buf.write("  <style>\n")
        buf.write(_DEFAULT_CSS)
        buf.write("  </style>\n</head>\n<body>\n")
        buf.write(f'  <main class="regulation" id="{html.escape(doc.id or doc.document_id or "doc")}">\n')
        buf.write(f"    <h1>{html.escape(title)}</h1>\n")
        if doc.document_id or doc.authority or doc.version:
            buf.write('    <dl class="doc-meta">\n')
            if doc.document_id:
                buf.write(f"      <dt>ID</dt><dd>{html.escape(doc.document_id)}</dd>\n")
            if doc.authority:
                buf.write(f"      <dt>Authority</dt><dd>{html.escape(doc.authority)}</dd>\n")
            if doc.version:
                buf.write(f"      <dt>Version</dt><dd>{html.escape(str(doc.version))}</dd>\n")
            buf.write("    </dl>\n")

        for child in doc.children:
            self._render_node(child, buf, level=2)

        buf.write("  </main>\n</body>\n</html>\n")
        slug = rule_file_slug(doc) if getattr(doc, "document_id", None) else "document"
        filename = f"{doc.document_id or slug or 'document'}.html"
        # sanitize filename
        filename = filename.replace("/", "-")
        return {filename: buf.getvalue()}

    def render_requirement(self, req: RegulationRequirement) -> dict[str, str]:
        buf = StringIO()
        title = f"{req.designation}: {req.title}".strip(": ")
        buf.write("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n")
        buf.write('  <meta charset="utf-8"/>\n')
        buf.write(f"  <title>{html.escape(title)}</title>\n")
        buf.write(f"  <style>\n{_DEFAULT_CSS}  </style>\n</head>\n<body>\n")
        buf.write(f'  <article class="requirement" id="{html.escape(req.id or req.designation)}">\n')
        buf.write(f"    <h1>{html.escape(title)}</h1>\n")
        if req.erules_id:
            buf.write(f'    <p class="erules-id"><strong>ERules ID:</strong> {html.escape(req.erules_id)}</p>\n')
        for child in req.children:
            self._render_node(child, buf, level=2)
        buf.write("  </article>\n</body>\n</html>\n")
        return {f"{rule_file_slug(req)}.html": buf.getvalue()}

    def _render_node(self, node: Node, buf: StringIO, level: int = 2) -> None:
        handler = getattr(self, f"_render_{node.type.value}", None) if node.type else None
        if handler:
            handler(node, buf, level)
        else:
            for child in node.children:
                self._render_node(child, buf, level)

    def _render_section(self, node: RegulationSection, buf: StringIO, level: int) -> None:
        h = min(level, 6)
        nid = html.escape(node.id or node.designation or "")
        label = html.escape(f"{node.designation}: {node.title}".strip(": "))
        buf.write(f'    <section id="{nid}">\n')
        buf.write(f"      <h{h}>{label}</h{h}>\n")
        for child in node.children:
            self._render_node(child, buf, level + 1)
        buf.write("    </section>\n")

    def _render_requirement(self, node: RegulationRequirement, buf: StringIO, level: int) -> None:
        self._render_topic_block(node, buf, level, "requirement")

    def _render_guidance(self, node: GuidanceNode, buf: StringIO, level: int) -> None:
        self._render_topic_block(node, buf, level, "guidance")

    def _render_acceptable_means_of_compliance(
        self, node: AcceptableMeansOfComplianceNode, buf: StringIO, level: int
    ) -> None:
        self._render_topic_block(node, buf, level, "amc")

    def _render_topic_block(self, node: Any, buf: StringIO, level: int, css: str) -> None:
        h = min(level, 6)
        nid = html.escape(node.id or node.designation or "")
        label = html.escape(f"{node.designation}: {node.title}".strip(": "))
        buf.write(f'    <section class="{css}" id="{nid}">\n')
        buf.write(f"      <h{h}>{label}</h{h}>\n")
        if getattr(node, "erules_id", None):
            buf.write(
                f'      <p class="erules-id"><strong>ERules ID:</strong> '
                f"{html.escape(node.erules_id)}</p>\n"
            )
        for child in node.children:
            self._render_node(child, buf, level + 1)
        buf.write("    </section>\n")

    def _render_paragraph(self, node: ParagraphNode, buf: StringIO, level: int) -> None:
        inline = self._render_inline_children(node)
        if inline.strip():
            buf.write(f"      <p>{inline}</p>\n")
        for child in node.children:
            if child.type not in (
                NodeType.TEXT,
                NodeType.BOLD,
                NodeType.ITALIC,
                NodeType.SUPERSCRIPT,
                NodeType.SUBSCRIPT,
                NodeType.HYPERLINK,
                NodeType.INTERNAL_REFERENCE,
                NodeType.LINE_BREAK,
            ):
                self._render_node(child, buf, level)

    def _render_heading(self, node: HeadingNode, buf: StringIO, level: int) -> None:
        h = min(max(node.level, 1), 6)
        text = self._render_inline_children(node)
        des = f"{html.escape(node.designation)}: " if node.designation else ""
        buf.write(f"      <h{h}>{des}{text}</h{h}>\n")

    def _render_list(self, node: ListNode, buf: StringIO, level: int) -> None:
        tag = "ol" if node.ordered else "ul"
        buf.write(f"      <{tag}>\n")
        for child in node.children:
            if isinstance(child, ListItemNode):
                text = self._render_inline_children(child)
                buf.write(f"        <li>{text}")
                for nested in child.children:
                    if isinstance(nested, ListNode):
                        self._render_list(nested, buf, level + 1)
                buf.write("</li>\n")
        buf.write(f"      </{tag}>\n")

    def _render_table(self, node: TableNode, buf: StringIO, level: int) -> None:
        buf.write("      <table>\n")
        if node.caption:
            buf.write(f"        <caption>{html.escape(node.caption)}</caption>\n")
        if node.headers:
            buf.write("        <thead>\n")
            for row in node.headers:
                buf.write("          <tr>\n")
                for cell in row:
                    if self._cell_should_skip(cell):
                        continue
                    attrs = self._cell_html_attrs(cell)
                    buf.write(f"            <th{attrs}>{self._render_cell(cell)}</th>\n")
                buf.write("          </tr>\n")
            buf.write("        </thead>\n")
        if node.rows:
            buf.write("        <tbody>\n")
            for row in node.rows:
                buf.write("          <tr>\n")
                for cell in row:
                    if self._cell_should_skip(cell):
                        continue
                    attrs = self._cell_html_attrs(cell)
                    buf.write(f"            <td{attrs}>{self._render_cell(cell)}</td>\n")
                buf.write("          </tr>\n")
            buf.write("        </tbody>\n")
        buf.write("      </table>\n")

    def _cell_meta(self, cell: Any) -> dict:
        if isinstance(cell, list) and cell:
            return dict(getattr(cell[0], "metadata", {}).get("cell") or {})
        if hasattr(cell, "metadata"):
            return dict(cell.metadata.get("cell") or {})
        return {}

    def _cell_should_skip(self, cell: Any) -> bool:
        meta = self._cell_meta(cell)
        return bool(meta.get("skip") or meta.get("vmerge") == "continue")

    def _cell_html_attrs(self, cell: Any) -> str:
        meta = self._cell_meta(cell)
        parts: list[str] = []
        colspan = meta.get("colspan")
        if colspan and str(colspan) not in ("", "1"):
            parts.append(f' colspan="{html.escape(str(colspan))}"')
        rowspan = meta.get("rowspan")
        if rowspan and str(rowspan) not in ("", "1"):
            parts.append(f' rowspan="{html.escape(str(rowspan))}"')
        return "".join(parts)

    def _render_cell(self, cell: Any) -> str:
        if isinstance(cell, list):
            parts: list[str] = []
            for item in cell:
                if isinstance(item, TableNode):
                    nested = StringIO()
                    self._render_table(item, nested, 0)
                    parts.append(nested.getvalue())
                else:
                    parts.append(self._render_inline_children(item))
            return "<br/>".join(parts)
        return self._render_inline_children(cell)

    def _render_figure(self, node: FigureNode, buf: StringIO, level: int) -> None:
        src = html.escape(f"{self.asset_prefix}/{node.image_path}")
        alt = html.escape(node.alt_text or node.caption or "Figure")
        buf.write("      <figure>\n")
        buf.write(f'        <img src="{src}" alt="{alt}"/>\n')
        if node.caption:
            buf.write(f"        <figcaption>{html.escape(node.caption)}</figcaption>\n")
        buf.write("      </figure>\n")

    def _render_inline_children(self, node: Node) -> str:
        return "".join(self._render_inline(child) for child in node.children)

    def _render_inline(self, node: Node) -> str:
        if isinstance(node, TextNode) or node.type == NodeType.TEXT:
            return html.escape(getattr(node, "text", "") or "")
        if isinstance(node, BoldNode) or node.type == NodeType.BOLD:
            return f"<strong>{self._render_inline_children(node) or html.escape(node.text)}</strong>"
        if isinstance(node, ItalicNode) or node.type == NodeType.ITALIC:
            return f"<em>{self._render_inline_children(node) or html.escape(node.text)}</em>"
        if isinstance(node, SuperscriptNode) or node.type == NodeType.SUPERSCRIPT:
            return f"<sup>{self._render_inline_children(node) or html.escape(node.text)}</sup>"
        if isinstance(node, SubscriptNode) or node.type == NodeType.SUBSCRIPT:
            return f"<sub>{self._render_inline_children(node) or html.escape(node.text)}</sub>"
        if isinstance(node, HyperlinkNode) or node.type == NodeType.HYPERLINK:
            label = self._render_inline_children(node) or html.escape(node.text)
            return f'<a href="{html.escape(node.url)}">{label}</a>'
        if isinstance(node, InternalReferenceNode) or node.type == NodeType.INTERNAL_REFERENCE:
            label = self._render_inline_children(node) or html.escape(
                node.text or node.target_designation
            )
            href = f"#{html.escape(node.target_id)}" if node.target_id else "#"
            return f'<a class="internal-ref" href="{href}">{label}</a>'
        if node.type == NodeType.LINE_BREAK:
            return "<br/>"
        return self._render_inline_children(node)


_DEFAULT_CSS = """
    body { font-family: system-ui, sans-serif; line-height: 1.5; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
    h1, h2, h3, h4 { line-height: 1.25; }
    .doc-meta { display: grid; grid-template-columns: auto 1fr; gap: 0.25rem 1rem; }
    .doc-meta dt { font-weight: 600; }
    table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
    th, td { border: 1px solid #ccc; padding: 0.4rem 0.6rem; vertical-align: top; }
    th { background: #f4f4f4; }
    figure { margin: 1rem 0; }
    img { max-width: 100%; height: auto; }
    .erules-id { color: #555; font-size: 0.95rem; }
    a.internal-ref { text-decoration: underline dotted; }
    section { margin: 1.5rem 0; }
"""


def render_html(
    doc: RegulationDocument | RegulationRequirement,
    asset_prefix: str = "assets",
) -> dict[str, str]:
    """Convenience: render document or single requirement to HTML."""
    renderer = HTMLRenderer(asset_prefix=asset_prefix)
    if isinstance(doc, RegulationDocument):
        return renderer.render(doc)
    if isinstance(doc, RegulationRequirement):
        return renderer.render_requirement(doc)
    raise TypeError(f"Unsupported type for HTML render: {type(doc)!r}")
