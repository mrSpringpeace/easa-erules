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

        self._parse_table_properties(elem, table)
        self._parse_table_grid(elem, table)

        rows_data = self._parse_rows(elem)
        table.headers = rows_data.get("headers", [])
        table.rows = rows_data.get("rows", [])

        # Post-process vertical merges into explicit rowspan counts
        self._apply_rowspans(table)

        table.caption = self._find_table_caption(elem)
        parent.add_child(table)

    def _parse_table_properties(self, elem: etree._Element, table: TableNode) -> None:
        """Parse table properties."""
        tbl_pr = elem.find(qname(W, "tblPr"))
        if tbl_pr is not None:
            style = tbl_pr.find(qname(W, "tblStyle"))
            if style is not None:
                table.metadata["style"] = style.get(qname(W, "val"))

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
        headers: list = []
        rows: list = []
        trs = elem.findall(qname(W, "tr"))

        for idx, tr in enumerate(trs):
            row_cells = []
            for tc in tr.findall(qname(W, "tc")):
                row_cells.append(self._parse_cell(tc))

            # First row is header by default; additional header rows if tblHeader set
            # and we have not yet started body rows.
            if idx == 0 or (not rows and self._has_tbl_header(tr)):
                headers.append(row_cells)
            else:
                rows.append(row_cells)

        return {"headers": headers, "rows": rows}

    def _has_tbl_header(self, tr: etree._Element) -> bool:
        tr_pr = tr.find(qname(W, "trPr"))
        if tr_pr is not None and tr_pr.find(qname(W, "tblHeader")) is not None:
            return True
        return False

    def _parse_cell(self, tc: etree._Element) -> list[Any]:
        """Parse a table cell (paragraphs and nested tables)."""
        content: list[Any] = []

        tc_pr = tc.find(qname(W, "tcPr"))
        cell_meta: dict[str, Any] = {}
        if tc_pr is not None:
            grid_span = tc_pr.find(qname(W, "gridSpan"))
            if grid_span is not None:
                cell_meta["colspan"] = grid_span.get(qname(W, "val"))

            v_merge = tc_pr.find(qname(W, "vMerge"))
            if v_merge is not None:
                # restart | continue (missing val == continue)
                cell_meta["vmerge"] = v_merge.get(qname(W, "val")) or "continue"

            tc_w = tc_pr.find(qname(W, "tcW"))
            if tc_w is not None:
                cell_meta["width"] = tc_w.get(qname(W, "w"))

        for child in tc:
            local = etree.QName(child.tag).localname
            if local == "p":
                para = ParagraphNode()
                self.parser.paragraph_parser._parse_paragraph_content(child, para)
                if cell_meta:
                    para.metadata["cell"] = dict(cell_meta)
                content.append(para)
            elif local == "tbl":
                # Nested table — parse as nested TableNode
                nested = TableNode()
                nested_parser = TableParser(self.parser)
                # Reuse row parsing without re-parenting to outer parent
                nested_parser._parse_table_properties(child, nested)
                nested_parser._parse_table_grid(child, nested)
                data = nested_parser._parse_rows(child)
                nested.headers = data["headers"]
                nested.rows = data["rows"]
                nested_parser._apply_rowspans(nested)
                if cell_meta:
                    nested.metadata["cell"] = dict(cell_meta)
                content.append(nested)

        # Ensure vmerge/colspan metadata is retained even on empty cells
        if not content and cell_meta:
            para = ParagraphNode()
            para.metadata["cell"] = dict(cell_meta)
            content.append(para)

        return content

    def _apply_rowspans(self, table: TableNode) -> None:
        """Convert OOXML vMerge chains into numeric rowspan on restart cells."""
        all_rows = table.headers + table.rows
        if not all_rows:
            return

        # Work column-by-column on logical grid is hard without expanded cells;
        # approximate: for each row/cell, if vmerge=restart, count following
        # continue cells in the same ordinal position.
        for r_idx, row in enumerate(all_rows):
            for c_idx, cell in enumerate(row):
                meta = _cell_meta(cell)
                if meta.get("vmerge") != "restart":
                    continue
                span = 1
                for r2 in range(r_idx + 1, len(all_rows)):
                    if c_idx >= len(all_rows[r2]):
                        break
                    meta2 = _cell_meta(all_rows[r2][c_idx])
                    if meta2.get("vmerge") == "continue":
                        span += 1
                        meta2["skip"] = True
                    else:
                        break
                if span > 1:
                    meta["rowspan"] = str(span)
                    _set_cell_meta(cell, meta)

    def _find_table_caption(self, elem: etree._Element) -> str | None:
        """Try to find table caption from nearby paragraphs."""
        prev = elem.getprevious()
        while prev is not None:
            if etree.QName(prev.tag).localname == "p":
                text = "".join(prev.itertext()).strip()
                if text.lower().startswith(("table", "figure", "fig.")):
                    return text
            prev = prev.getprevious()

        nxt = elem.getnext()
        while nxt is not None:
            if etree.QName(nxt.tag).localname == "p":
                text = "".join(nxt.itertext()).strip()
                if text.lower().startswith(("table", "figure", "fig.")):
                    return text
            nxt = nxt.getnext()

        return None


def _cell_meta(cell: Any) -> dict[str, Any]:
    if isinstance(cell, list) and cell:
        first = cell[0]
        return dict(getattr(first, "metadata", {}).get("cell") or {})
    if hasattr(cell, "metadata"):
        return dict(cell.metadata.get("cell") or {})
    return {}


def _set_cell_meta(cell: Any, meta: dict[str, Any]) -> None:
    if isinstance(cell, list) and cell:
        cell[0].metadata.setdefault("cell", {}).update(meta)
    elif hasattr(cell, "metadata"):
        cell.metadata.setdefault("cell", {}).update(meta)
