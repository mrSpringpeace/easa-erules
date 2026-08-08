"""EASA XML / OOXML namespace constants."""

from typing import Final

# WordprocessingML main document namespace
W: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# Relationships
REL: Final = "http://schemas.openxmlformats.org/package/2006/relationships"

# Content Types
CT: Final = "http://schemas.openxmlformats.org/package/2006/content-types"

# Dublin Core / Core Properties
DC: Final = "http://purl.org/dc/elements/1.1/"
DCTERMS: Final = "http://purl.org/dc/terms/"
CP: Final = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"

# Extended Properties
EP: Final = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

# Custom XML / EASA specific
# EASA eRules custom XML namespace (observed in documents)
ERULES: Final = "http://www.easa.europa.eu/erules"

# XML Schema Instance
XSI: Final = "http://www.w3.org/2001/XMLSchema-instance"

# VML / DrawingML
VML: Final = "urn:schemas-microsoft-com:vml"
DRAWING: Final = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC: Final = "http://schemas.openxmlformats.org/drawingml/2006/picture"

# Office document relationships
OFFICE_DOC_REL: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Flat OPC Package (Microsoft implementation)
FLAT_OPC: Final = "http://schemas.microsoft.com/office/2006/xmlPackage"

# Common namespace map for lxml
NSMAP: Final = {
    "w": W,
    "rel": REL,
    "ct": CT,
    "dc": DC,
    "dcterms": DCTERMS,
    "cp": CP,
    "ep": EP,
    "erules": ERULES,
    "xsi": XSI,
    "vml": VML,
    "drawing": DRAWING,
    "pic": PIC,
    "pkg": FLAT_OPC,
}


def qname(ns: str, local: str) -> str:
    """Create a Clark-notation qualified name."""
    return f"{{{ns}}}{local}"


# Pre-built qualified names for common elements
W_DOCUMENT = qname(W, "document")
W_BODY = qname(W, "body")
W_P = qname(W, "p")
W_R = qname(W, "r")
W_T = qname(W, "t")
W_TAB = qname(W, "tab")
W_BR = qname(W, "br")
W_PPR = qname(W, "pPr")
W_RPR = qname(W, "rPr")
W_PSTYLE = qname(W, "pStyle")
W_NUM_PR = qname(W, "numPr")
W_ILVL = qname(W, "ilvl")
W_IND = qname(W, "ind")
W_SPACING = qname(W, "spacing")
W_RSTYLE = qname(W, "rStyle")
W_B = qname(W, "b")
W_I = qname(W, "i")
W_U = qname(W, "u")
W_SZ = qname(W, "sz")
W_SZ_CS = qname(W, "szCs")
W_VERTICAL_ALIGN = qname(W, "vertAlign")
W_HYPERLINK = qname(W, "hyperlink")
W_DRAWING = qname(W, "drawing")
W_BLIP_FILL = qname(W, "blipFill")
W_BLIP = qname(W, "blip")
W_INLINE = qname(W, "inline")
W_GRAPHIC = qname(W, "graphic")
W_GRAPHIC_DATA = qname(W, "graphicData")
W_TBL = qname(W, "tbl")
W_TR = qname(W, "tr")
W_TC = qname(W, "tc")
W_TC_PR = qname(W, "tcPr")
W_GRID_SPAN = qname(W, "gridSpan")
W_V_MERGE = qname(W, "vMerge")
W_TC_W = qname(W, "tcW")
W_TBL_PR = qname(W, "tblPr")
W_TBL_GRID = qname(W, "tblGrid")
W_GRID_COL = qname(W, "gridCol")
W_TBL_LOOK = qname(W, "tblLook")
W_TBL_STYLE = qname(W, "tblStyle")

# EASA custom elements (observed in eRules documents)
ERULES_TOPIC = qname(ERULES, "topic")
ERULES_PARAGRAPH = qname(ERULES, "paragraph")
ERULES_ID = qname(ERULES, "id")
ERULES_TITLE = qname(ERULES, "title")
ERULES_METADATA = qname(ERULES, "metadata")
ERULES_REGULATORY_SOURCE = qname(ERULES, "regulatorySource")
ERULES_REGULATORY_SUBJECT = qname(ERULES, "regulatorySubject")
ERULES_TYPE_OF_CONTENT = qname(ERULES, "typeOfContent")
ERULES_TECHNICAL_SUBJECT = qname(ERULES, "technicalSubjectMatter")
ERULES_AIRCRAFT_CATEGORY = qname(ERULES, "aircraftCategory")
ERULES_AIRCRAFT_USE = qname(ERULES, "aircraftUse")
ERULES_APPLICABILITY_DATE = qname(ERULES, "applicabilityDate")
ERULES_AMENDED_BY = qname(ERULES, "amendedBy")

REL_ID = qname(REL, "Id")
REL_TYPE = qname(REL, "Type")
REL_TARGET = qname(REL, "Target")
REL_TARGET_MODE = qname(REL, "TargetMode")

CT_TYPES = qname(CT, "Types")
CT_DEFAULT = qname(CT, "Default")
CT_OVERRIDE = qname(CT, "Override")