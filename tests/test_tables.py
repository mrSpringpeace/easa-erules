"""Tests for table parsing and HTML colspan/rowspan rendering."""

from __future__ import annotations

from easa_erules.input.package import OpcPackage
from easa_erules.model import TableNode
from easa_erules.parser import EasaDocumentParser
from easa_erules.render import render_html, render_markdown

MERGED_TABLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<pkg:package xmlns:pkg="http://schemas.microsoft.com/office/2006/xmlPackage">
  <pkg:part pkg:name="/[Content_Types].xml" pkg:contentType="application/xml">
    <pkg:xmlData>
      <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
        <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
        <Default Extension="xml" ContentType="application/xml"/>
        <Override PartName="/word/document.xml"
          ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
      </Types>
    </pkg:xmlData>
  </pkg:part>
  <pkg:part pkg:name="/_rels/.rels" pkg:contentType="application/vnd.openxmlformats-package.relationships+xml">
    <pkg:xmlData>
      <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
        <Relationship Id="rId1"
          Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
          Target="word/document.xml"/>
      </Relationships>
    </pkg:xmlData>
  </pkg:part>
  <pkg:part pkg:name="/word/document.xml"
    pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml">
    <pkg:xmlData>
      <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                  xmlns:erules="http://www.easa.europa.eu/erules">
        <w:body>
          <erules:metadata>
            <erules:id>ERULES-TBL</erules:id>
            <erules:title>Table test</erules:title>
            <erules:typeOfContent>Certification Specification</erules:typeOfContent>
          </erules:metadata>
          <erules:topic>
            <erules:id>CS-T.1</erules:id>
            <erules:title>CS-T.1 Tables</erules:title>
            <erules:metadata>
              <erules:typeOfContent>Certification Specification</erules:typeOfContent>
            </erules:metadata>
            <w:tbl>
              <w:tr>
                <w:tc>
                  <w:tcPr><w:gridSpan w:val="2"/></w:tcPr>
                  <w:p><w:r><w:t>Merged header</w:t></w:r></w:p>
                </w:tc>
              </w:tr>
              <w:tr>
                <w:tc>
                  <w:tcPr><w:vMerge w:val="restart"/></w:tcPr>
                  <w:p><w:r><w:t>Span</w:t></w:r></w:p>
                </w:tc>
                <w:tc>
                  <w:p><w:r><w:t>A</w:t></w:r></w:p>
                </w:tc>
              </w:tr>
              <w:tr>
                <w:tc>
                  <w:tcPr><w:vMerge w:val="continue"/></w:tcPr>
                  <w:p/>
                </w:tc>
                <w:tc>
                  <w:p><w:r><w:t>B</w:t></w:r></w:p>
                </w:tc>
              </w:tr>
            </w:tbl>
          </erules:topic>
        </w:body>
      </w:document>
    </pkg:xmlData>
  </pkg:part>
</pkg:package>
"""


def test_merged_table_html_attributes(tmp_path):
    path = tmp_path / "merged.xml"
    path.write_text(MERGED_TABLE_XML, encoding="utf-8")
    result = EasaDocumentParser(OpcPackage.from_file(path)).parse()
    tables = result.document.find_all(
        __import__("easa_erules.model", fromlist=["NodeType"]).NodeType.TABLE
    )
    assert tables
    table = tables[0]
    assert isinstance(table, TableNode)
    # header has colspan on first cell
    header_meta = table.headers[0][0][0].metadata.get("cell", {})
    assert header_meta.get("colspan") == "2"
    # restart cell got rowspan 2
    body0 = table.rows[0][0][0].metadata.get("cell", {})
    assert body0.get("rowspan") == "2"

    html = next(iter(render_html(result.document).values()))
    assert 'colspan="2"' in html
    assert 'rowspan="2"' in html
    # continue cell not emitted as empty extra cell content alone
    assert "Merged header" in html

    md = next(iter(render_markdown(result.document).values()))
    # complex table → HTML fragment in markdown
    assert "<table>" in md
    assert 'colspan="2"' in md
