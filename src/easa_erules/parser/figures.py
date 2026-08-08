"""EASA figure/image parser."""

from typing import Any

from lxml import etree

from ..input.namespaces import (
    DRAWING,
    PIC,
    REL,
    W,
    qname,
)
from ..model import Asset, FigureNode


class FigureParser:
    """Parser for drawings and images in the document."""

    def __init__(self, parser):
        self.parser = parser
        self.figure_counter = 0

    def parse_inline_drawing(self, drawing_elem: etree._Element, parent: Any) -> None:
        """Parse an inline drawing element (from within a paragraph/run)."""
        # Find blip (image reference)
        blip = drawing_elem.find(f".//{{{DRAWING}}}blip")
        if blip is None:
            blip = drawing_elem.find(f".//{{{PIC}}}blip")

        if blip is not None:
            embed_rel = blip.get(qname(REL, "embed"))
            if embed_rel:
                self._create_figure_from_rel(embed_rel, parent, drawing_elem)

    def parse_drawing_element(self, drawing_elem: etree._Element, parent: Any) -> None:
        """Parse a standalone drawing element."""
        self.parse_inline_drawing(drawing_elem, parent)

    def _create_figure_from_rel(self, rel_id: str, parent: Any, drawing_elem: etree._Element) -> None:
        """Create a figure node from a relationship ID."""
        # Resolve relationship to get image part
        if not self.parser.doc_part or not self.parser.doc_part.relationships:
            return

        rel = self.parser.doc_part.relationships.get(rel_id)
        if not rel or not rel.target:
            return

        # Get image data from package
        image_part = self.parser.package.get_part(rel.target)
        if not image_part:
            return

        # Generate deterministic name
        self.figure_counter += 1
        doc_id = getattr(self.parser.document, 'document_id', 'doc')
        ext = self._get_extension(image_part.content_type)
        det_name = f"{doc_id}-fig-{self.figure_counter:02d}.{ext}"

        # Create asset
        asset = Asset(
            original_path=rel.target,
            content_type=image_part.content_type,
            data=image_part.data,
            deterministic_name=det_name,
            relationship_id=rel_id,
        )
        self.parser.assets.add(asset)

        # Extract caption from drawing properties or nearby text
        caption = self._extract_caption(drawing_elem)
        alt_text = self._extract_alt_text(drawing_elem)

        # Create figure node
        figure = FigureNode(
            image_path=det_name,
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
        # Check for docPr (drawing properties) with title
        doc_pr = drawing_elem.find(f".//{{{DRAWING}}}docPr")
        if doc_pr is not None:
            title = doc_pr.get("title") or doc_pr.get("descr")
            if title:
                return title

        # Could also check for nearby caption paragraphs
        # (would require parent context)
        return ""

    def _extract_alt_text(self, drawing_elem: etree._Element) -> str:
        """Extract alt text from drawing."""
        doc_pr = drawing_elem.find(f".//{{{DRAWING}}}docPr")
        if doc_pr is not None:
            descr = doc_pr.get("descr")
            if descr:
                return descr
        return ""

    def extract_all_images(self) -> list[Asset]:
        """Extract all images from the document."""
        images = []

        if not self.parser.doc_part:
            return images

        # Find all drawing elements in document
        doc_xml = self.parser.doc_part.xml()
        for drawing in doc_xml.findall(f".//{{{W}}}drawing"):
            self._extract_images_from_drawing(drawing, images)

        return images

    def _extract_images_from_drawing(self, drawing_elem: etree._Element, images: list[Asset]) -> None:
        """Recursively extract images from drawing element."""
        for blip in drawing_elem.findall(f".//{{{DRAWING}}}blip"):
            embed_rel = blip.get(qname(REL, "embed"))
            if embed_rel:
                self._add_image_from_rel(embed_rel, images)

        for blip in drawing_elem.findall(f".//{{{PIC}}}blip"):
            embed_rel = blip.get(qname(REL, "embed"))
            if embed_rel:
                self._add_image_from_rel(embed_rel, images)

    def _add_image_from_rel(self, rel_id: str, images: list[Asset]) -> None:
        """Add image from relationship to list."""
        if not self.parser.doc_part or not self.parser.doc_part.relationships:
            return

        rel = self.parser.doc_part.relationships.get(rel_id)
        if not rel or not rel.target:
            return

        image_part = self.parser.package.get_part(rel.target)
        if not image_part:
            return

        # Check if already added
        for existing in images:
            if existing.sha256 == image_part.data.__hash__():
                return

        ext = self._get_extension(image_part.content_type)
        det_name = f"image-{len(images)+1:03d}.{ext}"

        asset = Asset(
            original_path=rel.target,
            content_type=image_part.content_type,
            data=image_part.data,
            deterministic_name=det_name,
            relationship_id=rel_id,
        )
        images.append(asset)