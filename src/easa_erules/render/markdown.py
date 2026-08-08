"""Markdown renderer for Regulation AST."""

from io import StringIO
from typing import Any

from ..model import (
    AcceptableMeansOfComplianceNode,
    EasaMetadata,
    FigureNode,
    GuidanceNode,
    HeadingNode,
    ListItemNode,
    ListNode,
    Node,
    NodeType,
    ParagraphNode,
    ReferenceNode,
    RegulationDocument,
    RegulationRequirement,
    RegulationSection,
    TableNode,
)  # TableNode used for nested tables in cells
from ..util.ids import rule_file_slug
from .frontmatter import (
    generate_document_frontmatter,
    generate_requirement_frontmatter,
    generate_section_frontmatter,
)


class MarkdownRenderer:
    """Renderer for converting Regulation AST to Markdown."""

    def __init__(self, split_by_rule: bool = False, asset_prefix: str = "assets"):
        self.split_by_rule = split_by_rule
        self.asset_prefix = asset_prefix
        self.output_files: dict[str, str] = {}
        self.current_file: StringIO | None = None
        self.heading_offset = 0
        # designation -> relative markdown path (for split mode links)
        self._rule_paths: dict[str, str] = {}
        # Active relative asset path for the file currently being rendered
        self._active_asset_prefix = asset_prefix

    def render(self, doc: RegulationDocument) -> dict[str, str]:
        """Render document to Markdown.

        Returns dict of filename -> content.
        If split_by_rule is True, returns multiple files.
        """
        self.output_files = {}
        self._rule_paths = {}

        if self.split_by_rule:
            self._build_rule_path_index(doc)
            self._render_split(doc)
        else:
            self._render_single(doc)

        return self.output_files

    def render_requirement(self, req: RegulationRequirement) -> dict[str, str]:
        """Render a single requirement as one Markdown file."""
        self.output_files = {}
        self._rule_paths = {}
        buf = StringIO()
        easa_meta = None
        if req.metadata.get("easa"):
            easa_meta = EasaMetadata.from_dict(req.metadata["easa"])
        buf.write(generate_requirement_frontmatter(req, easa_meta))
        buf.write("\n\n")
        buf.write(f"# {req.designation}: {req.title}\n\n")
        if req.erules_id:
            buf.write(f"**ERules ID:** {req.erules_id}\n\n")
        for child in req.children:
            self._render_node(child, buf, level=2)
        slug = rule_file_slug(req)
        self.output_files[f"{slug}.md"] = buf.getvalue()
        return self.output_files

    def _build_rule_path_index(self, doc: RegulationDocument) -> None:
        for child in doc.children:
            if isinstance(
                child,
                (RegulationRequirement, GuidanceNode, AcceptableMeansOfComplianceNode),
            ):
                path = f"rules/{rule_file_slug(child)}.md"
                if child.designation:
                    self._rule_paths[child.designation] = path
                if child.erules_id:
                    self._rule_paths[child.erules_id] = path
            elif isinstance(child, RegulationSection):
                path = f"sections/{rule_file_slug(child)}.md"
                if child.designation:
                    self._rule_paths[child.designation] = path

    def _render_single(self, doc: RegulationDocument) -> None:
        """Render as single Markdown file."""
        self._active_asset_prefix = self.asset_prefix
        buf = StringIO()

        # Frontmatter
        easa_meta = None
        if doc.metadata.get("easa"):
            easa_meta = EasaMetadata.from_dict(doc.metadata["easa"])
        buf.write(generate_document_frontmatter(doc, easa_meta))
        buf.write("\n\n")

        # Document title
        if doc.title:
            buf.write(f"# {doc.title}\n\n")

        # Render children
        for child in doc.children:
            self._render_node(child, buf, level=1)

        self.output_files[f"{doc.document_id or 'document'}.md"] = buf.getvalue()

    def _render_split(self, doc: RegulationDocument) -> None:
        """Render split by rule/topic."""
        # Main index file (lives at output root → assets/ is sibling)
        self._active_asset_prefix = self.asset_prefix
        index_buf = StringIO()
        easa_meta = None
        if doc.metadata.get("easa"):
            easa_meta = EasaMetadata.from_dict(doc.metadata["easa"])
        index_buf.write(generate_document_frontmatter(doc, easa_meta))
        index_buf.write("\n\n")
        index_buf.write(f"# {doc.title}\n\n")

        if doc.document_id:
            index_buf.write(f"**Document ID:** {doc.document_id}\n\n")
        if doc.authority:
            index_buf.write(f"**Authority:** {doc.authority}\n\n")
        if doc.version:
            index_buf.write(f"**Version:** {doc.version}\n\n")

        index_buf.write("## Contents\n\n")

        # Render each top-level child as separate file
        for child in doc.children:
            if isinstance(child, (RegulationRequirement, GuidanceNode, AcceptableMeansOfComplianceNode)):
                self._render_rule_file(child, doc, index_buf)
            elif isinstance(child, RegulationSection):
                self._render_section_file(child, doc, index_buf)
            else:
                # Render inline in index
                self._render_node(child, index_buf, level=2)

        self.output_files["index.md"] = index_buf.getvalue()

    def _render_rule_file(self, rule: Any, doc: RegulationDocument, index_buf: StringIO) -> None:
        """Render a single rule to its own file."""
        filename = f"rules/{rule_file_slug(rule)}.md"
        # Rule files live under rules/ → assets are one level up
        self._active_asset_prefix = f"../{self.asset_prefix}"

        buf = StringIO()

        # Frontmatter
        easa_meta = None
        if rule.metadata.get("easa"):
            easa_meta = EasaMetadata.from_dict(rule.metadata["easa"])
        buf.write(generate_requirement_frontmatter(rule, easa_meta))
        buf.write("\n\n")

        # Title
        buf.write(f"# {rule.designation}: {rule.title}\n\n")

        # ERules ID
        if rule.erules_id:
            buf.write(f"**ERules ID:** {rule.erules_id}\n\n")

        # Render children
        for child in rule.children:
            self._render_node(child, buf, level=2)

        self.output_files[filename] = buf.getvalue()
        self._active_asset_prefix = self.asset_prefix

        # Add to index
        index_buf.write(f"- [{rule.designation}: {rule.title}]({filename})\n")

    def _render_section_file(self, section: RegulationSection, doc: RegulationDocument, index_buf: StringIO) -> None:
        """Render a section to its own file."""
        filename = f"sections/{rule_file_slug(section)}.md"
        self._active_asset_prefix = f"../{self.asset_prefix}"

        buf = StringIO()

        buf.write(generate_section_frontmatter(section))
        buf.write("\n\n")

        heading_level = min(section.level + 1, 6)
        buf.write(f"{'#' * heading_level} {section.designation}: {section.title}\n\n")

        for child in section.children:
            self._render_node(child, buf, level=heading_level + 1)

        self.output_files[filename] = buf.getvalue()
        self._active_asset_prefix = self.asset_prefix

        index_buf.write(f"- [{section.designation}: {section.title}]({filename})\n")

    def _render_node(self, node: Node, buf: StringIO, level: int = 1) -> None:
        """Dispatch rendering based on node type."""
        renderer = getattr(self, f"_render_{node.type.value}", None)
        if renderer:
            renderer(node, buf, level)
        else:
            # Fallback: render children
            for child in node.children:
                self._render_node(child, buf, level)

    def _render_document(self, node: RegulationDocument, buf: StringIO, level: int) -> None:
        for child in node.children:
            self._render_node(child, buf, level)

    def _render_section(self, node: RegulationSection, buf: StringIO, level: int) -> None:
        heading_level = min(level, 6)
        buf.write(f"{'#' * heading_level} {node.designation}: {node.title}\n\n")
        for child in node.children:
            self._render_node(child, buf, level + 1)

    def _render_requirement(self, node: RegulationRequirement, buf: StringIO, level: int) -> None:
        heading_level = min(level, 6)
        buf.write(f"{'#' * heading_level} {node.designation}: {node.title}\n\n")
        if node.erules_id:
            buf.write(f"**ERules ID:** {node.erules_id}\n\n")
        for child in node.children:
            self._render_node(child, buf, level + 1)

    def _render_guidance(self, node: GuidanceNode, buf: StringIO, level: int) -> None:
        heading_level = min(level, 6)
        buf.write(f"{'#' * heading_level} {node.designation}: {node.title}\n\n")
        if node.erules_id:
            buf.write(f"**ERules ID:** {node.erules_id}\n\n")
        for child in node.children:
            self._render_node(child, buf, level + 1)

    def _render_acceptable_means_of_compliance(self, node: AcceptableMeansOfComplianceNode, buf: StringIO, level: int) -> None:
        heading_level = min(level, 6)
        buf.write(f"{'#' * heading_level} {node.designation}: {node.title}\n\n")
        if node.erules_id:
            buf.write(f"**ERules ID:** {node.erules_id}\n\n")
        for child in node.children:
            self._render_node(child, buf, level + 1)

    def _render_paragraph(self, node: ParagraphNode, buf: StringIO, level: int) -> None:
        # First render inline children (text content)
        text = self._render_inline_children(node)
        if text.strip():
            buf.write(f"{text}\n\n")

        # Then render any block-level children (figures, etc.)
        for child in node.children:
            if child.type not in (NodeType.TEXT, NodeType.BOLD, NodeType.ITALIC, 
                                   NodeType.SUPERSCRIPT, NodeType.SUBSCRIPT,
                                   NodeType.HYPERLINK, NodeType.INTERNAL_REFERENCE,
                                   NodeType.LINE_BREAK):
                self._render_node(child, buf, level)

    def _render_heading(self, node: HeadingNode, buf: StringIO, level: int) -> None:
        heading_level = min(level, 6)
        text = self._render_inline_children(node)
        designation = f"{node.designation}: " if node.designation else ""
        buf.write(f"{'#' * heading_level} {designation}{text}\n\n")

    def _render_list(self, node: ListNode, buf: StringIO, level: int) -> None:
        for i, child in enumerate(node.children):
            if isinstance(child, ListItemNode):
                self._render_list_item(child, buf, level, i + 1, node.ordered)

    def _render_list_item(self, node: ListItemNode, buf: StringIO, level: int, index: int, ordered: bool) -> None:
        prefix = f"{index}. " if ordered else "- "
        buf.write(f"{prefix}")
        text = self._render_inline_children(node)
        buf.write(f"{text}\n")

        # Nested lists
        for child in node.children:
            if isinstance(child, ListNode):
                self._render_list(child, buf, level + 1)

    def _render_table(self, node: TableNode, buf: StringIO, level: int) -> None:
        if node.caption:
            buf.write(f"**{node.caption}**\n\n")

        # Check if table is simple enough for Markdown
        if self._is_simple_table(node):
            self._render_markdown_table(node, buf)
        else:
            # Complex table: render as HTML
            self._render_html_table(node, buf)

        buf.write("\n")

    def _is_simple_table(self, node: TableNode) -> bool:
        """Check if table can be rendered as simple Markdown."""
        # Check for merged cells, nested tables
        all_rows = node.headers + node.rows
        for row in all_rows:
            for cell in row:
                if isinstance(cell, list):
                    for item in cell:
                        if item.metadata.get("cell", {}).get("colspan") or \
                           item.metadata.get("cell", {}).get("rowspan"):
                            return False
        return True

    def _render_markdown_table(self, node: TableNode, buf: StringIO) -> None:
        """Render table as Markdown."""
        all_rows = node.headers + node.rows
        if not all_rows:
            return

        # Determine column count
        max_cols = max(len(row) for row in all_rows)

        # Header row
        header_cells = []
        for i in range(max_cols):
            cell_text = ""
            if i < len(node.headers[0]) if node.headers else False:
                cell_text = self._render_cell_content(node.headers[0][i])
            header_cells.append(cell_text or " ")

        buf.write("| " + " | ".join(header_cells) + " |\n")
        buf.write("| " + " | ".join(["---"] * max_cols) + " |\n")

        # Data rows
        for row in node.rows:
            cells = []
            for i in range(max_cols):
                cell_text = ""
                if i < len(row):
                    cell_text = self._render_cell_content(row[i])
                cells.append(cell_text or " ")
            buf.write("| " + " | ".join(cells) + " |\n")

    def _render_html_table(self, node: TableNode, buf: StringIO) -> None:
        """Render table as HTML (supports colspan/rowspan from cell metadata)."""
        buf.write("<table>\n")

        if node.headers:
            buf.write("  <thead>\n")
            for row in node.headers:
                buf.write("    <tr>\n")
                for cell in row:
                    if self._cell_should_skip(cell):
                        continue
                    attrs = self._cell_html_attrs(cell)
                    buf.write(f"      <th{attrs}>{self._render_cell_content(cell)}</th>\n")
                buf.write("    </tr>\n")
            buf.write("  </thead>\n")

        if node.rows:
            buf.write("  <tbody>\n")
            for row in node.rows:
                buf.write("    <tr>\n")
                for cell in row:
                    if self._cell_should_skip(cell):
                        continue
                    attrs = self._cell_html_attrs(cell)
                    buf.write(f"      <td{attrs}>{self._render_cell_content(cell)}</td>\n")
                buf.write("    </tr>\n")
            buf.write("  </tbody>\n")

        buf.write("</table>\n")

    def _cell_meta(self, cell: Any) -> dict:
        if isinstance(cell, list) and cell:
            return dict(getattr(cell[0], "metadata", {}).get("cell") or {})
        if hasattr(cell, "metadata"):
            return dict(cell.metadata.get("cell") or {})
        return {}

    def _cell_should_skip(self, cell: Any) -> bool:
        meta = self._cell_meta(cell)
        if meta.get("skip"):
            return True
        # OOXML continuation cells of a vertical merge
        return meta.get("vmerge") == "continue"

    def _cell_html_attrs(self, cell: Any) -> str:
        meta = self._cell_meta(cell)
        parts: list[str] = []
        colspan = meta.get("colspan")
        if colspan and str(colspan) not in ("", "1"):
            parts.append(f' colspan="{colspan}"')
        rowspan = meta.get("rowspan")
        if rowspan and str(rowspan) not in ("", "1"):
            parts.append(f' rowspan="{rowspan}"')
        return "".join(parts)

    def _render_cell_content(self, cell: Any) -> str:
        """Render cell content to string."""
        if isinstance(cell, list):
            parts = []
            for item in cell:
                if isinstance(item, TableNode):
                    # Nested table as HTML fragment
                    nested = StringIO()
                    self._render_html_table(item, nested)
                    parts.append(nested.getvalue())
                elif isinstance(item, ParagraphNode):
                    parts.append(self._render_inline_children(item))
                else:
                    parts.append(self._render_inline_children(item))
            return "<br>".join(parts)
        elif isinstance(cell, ParagraphNode):
            return self._render_inline_children(cell)
        else:
            return self._render_inline_children(cell)

    def _render_figure(self, node: FigureNode, buf: StringIO, level: int) -> None:
        asset_path = f"{self._active_asset_prefix}/{node.image_path}"
        alt = node.alt_text or node.caption or "Figure"
        buf.write(f"![{alt}]({asset_path})\n")
        if node.caption:
            buf.write(f"*{node.caption}*\n")
        buf.write("\n")

    def _render_reference(self, node: ReferenceNode, buf: StringIO, level: int) -> None:
        if node.target_designation:
            buf.write(f"[{node.target_designation}]")
        buf.write("\n")

    # Inline rendering
    def _render_inline_children(self, node: Node) -> str:
        parts = []
        for child in node.children:
            parts.append(self._render_inline_node(child))
        return "".join(parts)

    def _render_inline_node(self, node: Node) -> str:
        if node.type == NodeType.TEXT:
            return node.text
        elif node.type == NodeType.BOLD:
            return f"**{self._render_inline_children(node)}**"
        elif node.type == NodeType.ITALIC:
            return f"*{self._render_inline_children(node)}*"
        elif node.type == NodeType.SUPERSCRIPT:
            return f"<sup>{self._render_inline_children(node)}</sup>"
        elif node.type == NodeType.SUBSCRIPT:
            return f"<sub>{self._render_inline_children(node)}</sub>"
        elif node.type == NodeType.HYPERLINK:
            return f"[{self._render_inline_children(node)}]({node.url})"
        elif node.type == NodeType.INTERNAL_REFERENCE:
            label = self._render_inline_children(node) or node.text or node.target_designation
            # Prefer split-mode rule file links when available
            path = self._rule_paths.get(node.target_designation) if node.target_designation else None
            if path:
                return f"[{label}]({path})"
            if node.target_id:
                return f"[{label}](#{node.target_id})"
            if node.target_designation:
                return f"[{label}]"
            return f"[{label}]"
        elif node.type == NodeType.LINE_BREAK:
            return "\n"
        else:
            # Fallback: render children
            return self._render_inline_children(node)


def render_markdown(
    doc: RegulationDocument | RegulationRequirement,
    split_by_rule: bool = False,
    asset_prefix: str = "assets",
) -> dict[str, str]:
    """Convenience function to render document (or single requirement) to Markdown."""
    renderer = MarkdownRenderer(split_by_rule=split_by_rule, asset_prefix=asset_prefix)
    if isinstance(doc, RegulationDocument):
        return renderer.render(doc)
    if isinstance(doc, RegulationRequirement):
        return renderer.render_requirement(doc)
    raise TypeError(f"Unsupported node type for markdown render: {type(doc)!r}")
