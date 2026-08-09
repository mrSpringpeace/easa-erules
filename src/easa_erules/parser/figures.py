"""EASA figure/image parser."""

from typing import Any

from lxml import etree

from ..input.namespaces import (
    DRAWING,
    OFFICE_DOC_REL,
    PIC,
    W,
)
from ..model import Asset, FigureNode
from ..util.slugify import slugify_rule

# WordprocessingDrawing namespace
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


class FigureParser:
    """Parser for drawings and images in the document."""

    def __init__(self, parser):
        self.parser = parser
        self.figure_counter = 0
        self._per_rule_counters: dict[str, int] = {}

    def parse_inline_drawing(self, drawing_elem: etree._Element, parent: Any) -> None:
        """Parse an inline drawing element (from within a paragraph/run)."""
        # Find blip (image reference)
        blip = drawing_elem.find(f".//{{{DRAWING}}}blip")
        if blip is None:
            blip = drawing_elem.find(f".//{{{PIC}}}blip")

        if blip is not None:
            embed_rel = blip.get(f"{{{OFFICE_DOC_REL}}}embed")
            if embed_rel:
                self._create_figure_from_rel(embed_rel, parent, drawing_elem)

    def parse_drawing_element(self, drawing_elem: etree._Element, parent: Any) -> None:
        """Parse a standalone drawing element."""
        self.parse_inline_drawing(drawing_elem, parent)

    def _ancestor_rule_slug(self, parent: Any) -> str:
        """Walk parent chain for a rule designation to use in asset names."""
        node = parent
        while node is not None:
            designation = getattr(node, "designation", "") or ""
            erules_id = getattr(node, "erules_id", "") or ""
            for candidate in (designation, erules_id):
                if candidate and not candidate.upper().startswith("ERULES"):
                    return slugify_rule(candidate)
            node = getattr(node, "parent", None)

        doc = getattr(self.parser, "document", None)
        if doc is not None:
            doc_id = getattr(doc, "document_id", "") or ""
            if doc_id:
                return slugify_rule(doc_id)
        return "doc"

    def _create_figure_from_rel(self, rel_id: str, parent: Any, drawing_elem: etree._Element) -> None:
        """Create a figure node from a relationship ID."""
        if not self.parser.doc_part or not self.parser.doc_part.relationships:
            return

        rel = self.parser.doc_part.relationships.get(rel_id)
        if not rel or not rel.target:
            return

        # Resolve target against the document part (OPC) with fallbacks
        image_part = self.parser.package.resolve_part(
            rel.target,
            source_part_path=self.parser.doc_part.path,
        )
        if not image_part:
            return

        rule_slug = self._ancestor_rule_slug(parent)
        self._per_rule_counters[rule_slug] = self._per_rule_counters.get(rule_slug, 0) + 1
        self.figure_counter += 1
        ext = self._get_extension(image_part.content_type)
        det_name = f"{rule_slug}-fig-{self._per_rule_counters[rule_slug]:02d}.{ext}"

        asset = Asset(
            original_path=rel.target,
            content_type=image_part.content_type,
            data=image_part.data,
            deterministic_name=det_name,
            relationship_id=rel_id,
        )
        stored = self.parser.assets.add(asset)

        caption = self._extract_caption(drawing_elem)
        alt_text = self._extract_alt_text(drawing_elem)

        figure = FigureNode(
            image_path=stored.deterministic_name,
            caption=caption,
            alt_text=alt_text,
        )
        parent.add_child(figure)

    def _get_extension(self, content_type: str) -> str:
        """Get file extension from MIME type."""
        mapping = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/gif": "gif",
            "image/bmp": "bmp",
            "image/tiff": "tiff",
            "image/webp": "webp",
        }
        return mapping.get(content_type, "png")

    def _extract_caption(self, drawing_elem: etree._Element) -> str:
        """Extract caption from drawing element or nearby."""
        doc_pr = drawing_elem.find(f".//{{{WP}}}docPr")
        if doc_pr is not None:
            title = doc_pr.get("title") or doc_pr.get("descr")
            if title:
                return title

        doc_pr = drawing_elem.find(f".//{{{DRAWING}}}docPr")
        if doc_pr is not None:
            title = doc_pr.get("title") or doc_pr.get("descr")
            if title:
                return title

        return ""

    def _extract_alt_text(self, drawing_elem: etree._Element) -> str:
        """Extract alt text from drawing."""
        doc_pr = drawing_elem.find(f".//{{{WP}}}docPr")
        if doc_pr is not None:
            descr = doc_pr.get("descr")
            if descr:
                return descr

        doc_pr = drawing_elem.find(f".//{{{DRAWING}}}docPr")
        if doc_pr is not None:
            descr = doc_pr.get("descr")
            if descr:
                return descr

        return ""

    def extract_all_images(self) -> list[Asset]:
        """Extract all images from the document."""
        images: list[Asset] = []

        if not self.parser.doc_part:
            return images

        doc_xml = self.parser.doc_part.xml()
        for drawing in doc_xml.findall(f".//{{{W}}}drawing"):
            self._extract_images_from_drawing(drawing, images)

        return images

    def _extract_images_from_drawing(self, drawing_elem: etree._Element, images: list[Asset]) -> None:
        """Recursively extract images from drawing element."""
        for blip in drawing_elem.findall(f".//{{{DRAWING}}}blip"):
            embed_rel = blip.get(f"{{{OFFICE_DOC_REL}}}embed")
            if embed_rel:
                self._add_image_from_rel(embed_rel, images)

        for blip in drawing_elem.findall(f".//{{{PIC}}}blip"):
            embed_rel = blip.get(f"{{{OFFICE_DOC_REL}}}embed")
            if embed_rel:
                self._add_image_from_rel(embed_rel, images)

    def _add_image_from_rel(self, rel_id: str, images: list[Asset]) -> None:
        """Add image from relationship to list."""
        if not self.parser.doc_part or not self.parser.doc_part.relationships:
            return

        rel = self.parser.doc_part.relationships.get(rel_id)
        if not rel or not rel.target:
            return

        image_part = self.parser.package.resolve_part(
            rel.target,
            source_part_path=self.parser.doc_part.path,
        )
        if not image_part:
            return

        import hashlib
        content_hash = hashlib.sha256(image_part.data).hexdigest()
        for existing in images:
            if existing.sha256 == content_hash:
                return

        ext = self._get_extension(image_part.content_type)
        det_name = f"image-{len(images) + 1:03d}.{ext}"

        asset = Asset(
            original_path=rel.target,
            content_type=image_part.content_type,
            data=image_part.data,
            deterministic_name=det_name,
            relationship_id=rel_id,
        )
        images.append(asset)
