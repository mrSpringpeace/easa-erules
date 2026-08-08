"""EASA metadata parser."""

from typing import Any

from lxml import etree

from ..input.namespaces import (
    ERULES,
    NSMAP,
)
from ..model import EasaMetadata


class MetadataParser:
    """Parser for EASA document metadata."""

    def __init__(self, parser):
        self.parser = parser

    def parse(self, root: etree._Element) -> None:
        """Parse metadata from document root."""
        doc = self.parser.document
        if not doc:
            return

        # Find EASA metadata element
        meta_elem = root.find(f".//{{{ERULES}}}metadata")
        if meta_elem is None:
            # Try alternative locations
            meta_elem = root.find(".//erules:metadata", namespaces=NSMAP)

        if meta_elem is not None:
            meta = self._parse_metadata_element(meta_elem)
            doc.easa_metadata = meta.to_dict()
            doc.metadata["easa"] = meta.to_dict()

            # Set document-level fields
            if meta.source_title:
                doc.title = meta.source_title
            if meta.erules_id:
                doc.document_id = meta.erules_id

    def _parse_metadata_element(self, elem: etree._Element) -> EasaMetadata:
        """Parse a single metadata element."""
        meta = EasaMetadata()

        # ERulesId
        erules_id_elem = elem.find(f".//{{{ERULES}}}id")
        if erules_id_elem is not None:
            meta.erules_id = erules_id_elem.text or ""

        # Source title
        title_elem = elem.find(f".//{{{ERULES}}}title")
        if title_elem is not None:
            meta.source_title = title_elem.text or ""

        # RegulatorySource
        for src in elem.findall(f".//{{{ERULES}}}regulatorySource"):
            if src.text:
                meta.regulatory_source.append(src.text)

        # RegulatorySubject
        for subj in elem.findall(f".//{{{ERULES}}}regulatorySubject"):
            if subj.text:
                meta.regulatory_subject.append(subj.text)

        # TypeOfContent
        for toc in elem.findall(f".//{{{ERULES}}}typeOfContent"):
            if toc.text:
                meta.type_of_content.append(toc.text)

        # TechnicalSubjectMatter
        for tsm in elem.findall(f".//{{{ERULES}}}technicalSubjectMatter"):
            if tsm.text:
                meta.technical_subject_matter.append(tsm.text)

        # AircraftCategory
        for ac in elem.findall(f".//{{{ERULES}}}aircraftCategory"):
            if ac.text:
                meta.aircraft_category.append(ac.text)

        # AircraftUse
        for au in elem.findall(f".//{{{ERULES}}}aircraftUse"):
            if au.text:
                meta.aircraft_use.append(au.text)

        # ApplicabilityDate
        app_date = elem.find(f".//{{{ERULES}}}applicabilityDate")
        if app_date is not None:
            meta.applicability_date = app_date.text

        # AmendedBy
        for ab in elem.findall(f".//{{{ERULES}}}amendedBy"):
            if ab.text:
                meta.amended_by.append(ab.text)

        # Store raw attributes for preservation
        for child in elem:
            tag = etree.QName(child.tag).localname
            if child.text:
                meta.raw_attributes[tag] = child.text

        return meta

    def parse_nested(self, elem: etree._Element, parent: Any) -> None:
        """Parse nested metadata (e.g., within a topic)."""
        meta = self._parse_metadata_element(elem)
        if hasattr(parent, 'metadata'):
            parent.metadata["easa"] = meta.to_dict()