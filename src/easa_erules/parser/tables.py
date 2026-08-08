"""EASA table parser."""

from typing import Any

from lxml import etree

from ..input.namespaces import (
    W,
    qname,
)
from ..model import ParagraphNode, TableNode


class TableParser:
    """Parser for WordprocessingML tables."""

    def __init__(self, parser):
        self.parser = parser

    def parse(self, elem: etree._Element, parent: Any) -> None:
        """Parse a table element."""
        table = TableNode()

        # Parse table properties
        self._parse_table_properties(elem, table)

        # Parse table grid (column widths)
        self._parse_table_grid(elem, table)

        # Parse rows
        rows_data = self._parse_rows(elem)
        table.headers = rows_data.get("headers", [])
        table.rows = rows_data.get("rows", [])

        # Try to extract caption from preceding/following paragraph
        table.caption = self._find_table_caption(elem)

        parent.add_child(table)

    def _parse_table_properties(self, elem: etree._Element, table: TableNode) -> None:
        """Parse table properties."""
        tbl_pr = elem.find(qname(W, "tblPr"))
        if tbl_pr is not None:
            # Table style
            style = tbl_pr.find(qname(W, "tblStyle"))
            if style is not None:
                table.metadata["style"] = style.get(qname(W, "val"))

            # Table look
            look = tbl_pr.find(qname(W, "tblLook"))
            if look is not None:
                table.metadata["look"] = look.get(qname(W, "val"))

    def _parse_table_grid(self, elem: etree._Element, table: TableNode) -> None:
        """Parse table grid (column definitions)."""
        grid = elem.find(qname(W, "tblGrid"))
        if grid is not None:
            cols = []
            for col in grid.findall(qname(W, "gridCol")):
                width = col.get(qname(W, "w"))
                cols.append({"width": width})
            table.metadata["grid"] = cols

    def _parse_rows(self, elem: etree._Element) -> dict:
        """Parse all rows in the table."""
        headers = []
        rows = []
        is_header = True

        for tr in elem.findall(qname(W, "tr")):
            row_cells = []
            for tc in tr.findall(qname(W, "tc")):
                cell_content = self._parse_cell(tc)
                row_cells.append(cell_content)

            if is_header and self._is_header_row(tr):
                headers.append(row_cells)
            else:
                is_header = False
                rows.append(row_cells)

        return {"headers": headers, "rows": rows}

    def _is_header_row(self, tr: etree._Element) -> bool:
        """Check if row is a header row."""
        # Check for table header style or first row
        tr_pr = tr.find(qname(W, "trPr"))
        if tr_pr is not None:
            # Could check for specific header properties
            pass
        return True  # First row is header by default

    def _parse_cell(self, tc: etree._Element) -> list[Any]:
        """Parse a table cell."""
        content = []

        # Cell properties
        tc_pr = tc.find(qname(W, "tcPr"))
        cell_meta = {}
        if tc_pr is not None:
            # Grid span (colspan)
            grid_span = tc_pr.find(qname(W, "gridSpan"))
            if grid_span is not None:
                cell_meta["colspan"] = grid_span.get(qname(W, "val"))

            # Vertical merge (rowspan)
            v_merge = tc_pr.find(qname(W, "vMerge"))
            if v_merge is not None:
                cell_meta["rowspan"] = v_merge.get(qname(W, "val"), "continue")

            # Cell width
            tc_w = tc_pr.find(qname(W, "tcW"))
            if tc_w is not None:
                cell_meta["width"] = tc_w.get(qname(W, "w"))

        # Parse cell content (paragraphs)
        for child in tc:
            if etree.QName(child.tag).localname == "p":
                para = ParagraphNode()
                self.parser.paragraph_parser._parse_paragraph_content(child, para)
                if cell_meta:
                    para.metadata["cell"] = cell_meta
                content.append(para)

        return content

    def _find_table_caption(self, elem: etree._Element) -> str | None:
        """Try to find table caption from nearby paragraphs."""
        # Check previous sibling
        prev = elem.getprevious()
        while prev is not None:
            if etree.QName(prev.tag).localname == "p":
                text = "".join(prev.itertext()).strip()
                if text.lower().startswith(("table", "figure", "fig.")):
                    return text
            prev = prev.getprevious()

        # Check next sibling
        nxt = elem.getnext()
        while nxt is not None:
            if etree.QName(nxt.tag).localname == "p":
                text = "".join(nxt.itertext()).strip()
                if text.lower().startswith(("table", "figure", "fig.")):
                    return text
            nxt = nxt.getnext()

        return None