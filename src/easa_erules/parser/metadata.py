"""EASA metadata parser (inline XML, customXml export package, core props)."""

from __future__ import annotations

from typing import Any

from lxml import etree

from ..input.namespaces import (
    CP,
    DC,
    DCTERMS,
    ERULES,
    ERULES_EXPORT,
    NSMAP,
)
from ..model import EasaMetadata
from ..model.metadata import normalize_easa_metadata_dict


class MetadataParser:
    """Parser for EASA document metadata from multiple package sources."""

    def __init__(self, parser):
        self.parser = parser
        # sdt-id (string) → normalized topic metadata dict
        self.export_topics_by_sdt_id: dict[str, dict[str, Any]] = {}
        self.export_document: dict[str, Any] = {}

    def parse(self, root: etree._Element) -> None:
        """Parse metadata from document root, export customXml, and core props."""
        doc = self.parser.document
        if not doc:
            return

        # 1) Official erules-export customXml (richest source on real EAR packages)
        self._load_export_custom_xml()
        if self.export_document:
            meta = EasaMetadata.from_dict(self.export_document)
            doc.easa_metadata = meta.to_dict()
            doc.metadata["easa"] = meta.to_dict()
            if meta.source_title and not doc.title:
                doc.title = meta.source_title
            if meta.erules_id and not doc.document_id:
                doc.document_id = meta.erules_id
            if meta.guid:
                doc.metadata.setdefault("package", {})["guid"] = meta.guid
            if meta.pub_time:
                doc.metadata.setdefault("package", {})["pub_time"] = meta.pub_time

        # 2) Inline erules:metadata in the Word document (fixtures + some exports)
        meta_elem = root.find(f".//{{{ERULES}}}metadata")
        if meta_elem is None:
            meta_elem = root.find(".//erules:metadata", namespaces=NSMAP)
        if meta_elem is None:
            meta_elem = root.find(f".//{{{ERULES_EXPORT}}}metadata")

        if meta_elem is not None:
            meta = self._parse_metadata_element(meta_elem)
            inline = meta.to_dict()
            existing = dict(doc.easa_metadata or {})
            if existing:
                merged = {**inline, **existing}
                # Overlay non-empty inline values on top of export defaults
                for key, value in inline.items():
                    if value is None or value == "" or value == []:
                        continue
                    if isinstance(value, list) and isinstance(merged.get(key), list):
                        merged[key] = list(dict.fromkeys([*merged[key], *value]))
                    else:
                        merged[key] = value
                # Keep stable core keys from inline when export omitted them
                for key, value in inline.items():
                    merged.setdefault(key, value)
            else:
                merged = inline
            doc.easa_metadata = merged
            doc.metadata["easa"] = dict(merged)
            if meta.source_title:
                doc.title = meta.source_title
            if meta.erules_id:
                doc.document_id = meta.erules_id

        # 3) OOXML core properties (title, dates)
        self._load_core_properties()

    def topic_meta_for_sdt(self, sdt_id: str | None) -> dict[str, Any] | None:
        """Look up export metadata for a Word SDT id."""
        if not sdt_id:
            return None
        return self.export_topics_by_sdt_id.get(str(sdt_id))

    def _load_export_custom_xml(self) -> None:
        """Find ``erules-export`` customXml parts and index topics by sdt-id."""
        package = getattr(self.parser, "package", None)
        if package is None:
            return

        for path, part in package.get_all_parts().items():
            # Skip relationship / props sidecars
            lower = path.lower()
            if "customxml" not in lower.replace("\\", "/"):
                continue
            if "props" in lower or lower.endswith(".rels"):
                continue
            data = part.data or b""
            if b"erules-export" not in data[:4000] and b"erules-export" not in data:
                continue
            try:
                root = etree.fromstring(data)
            except etree.XMLSyntaxError:
                continue
            if not isinstance(root.tag, str):
                continue
            ns = etree.QName(root.tag).namespace or ""
            local = etree.QName(root.tag).localname
            if ns != ERULES_EXPORT or local != "document":
                continue

            self._ingest_export_document(root)
            break  # one export document is enough

    def _ingest_export_document(self, root: etree._Element) -> None:
        """Index document-level attrs and per-topic export metadata."""
        raw_doc = dict(root.attrib)
        self.export_document = normalize_easa_metadata_dict(raw_doc)
        # Preserve map/pub URLs in raw_attributes for reproducibility
        package_extras = {
            k: v
            for k, v in raw_doc.items()
            if k
            in (
                "map-url",
                "pub-template-url",
                "xslt-url",
                "guid",
                "pub-time",
                "source-title",
            )
            and v
        }
        if package_extras:
            raw = dict(self.export_document.get("raw_attributes") or {})
            raw.update(package_extras)
            self.export_document["raw_attributes"] = raw

        self.export_topics_by_sdt_id.clear()
        for topic in root.findall(f".//{{{ERULES_EXPORT}}}topic"):
            attrs = dict(topic.attrib)
            sdt_id = attrs.get("sdt-id") or attrs.get("sdt_id") or ""
            if not sdt_id:
                continue
            normalized = normalize_easa_metadata_dict(attrs)
            # Keep original source-title with NBSP cleaned
            title = attrs.get("source-title") or normalized.get("source_title") or ""
            if title:
                normalized["source_title"] = title.replace("\xa0", " ").strip()
            normalized["sdt_id"] = str(sdt_id)
            self.export_topics_by_sdt_id[str(sdt_id)] = normalized

    def _load_core_properties(self) -> None:
        """Merge Dublin Core / core properties into document metadata."""
        package = getattr(self.parser, "package", None)
        doc = self.parser.document
        if package is None or doc is None:
            return

        core = package.get_part("docProps/core.xml")
        if core is None:
            return
        try:
            root = core.xml()
        except etree.XMLSyntaxError:
            return

        core_meta: dict[str, Any] = {}
        title_el = root.find(f".//{{{DC}}}title")
        if title_el is not None and title_el.text:
            core_meta["title"] = title_el.text.strip()
            if not doc.title:
                doc.title = title_el.text.strip()

        for local, key in (
            ("created", "created"),
            ("modified", "modified"),
        ):
            el = root.find(f".//{{{DCTERMS}}}{local}")
            if el is not None and el.text:
                core_meta[key] = el.text.strip()

        rev = root.find(f".//{{{CP}}}revision")
        if rev is not None and rev.text:
            core_meta["revision"] = rev.text.strip()

        if core_meta:
            doc.metadata.setdefault("core_properties", {}).update(core_meta)

        app = package.get_part("docProps/app.xml")
        if app is not None:
            try:
                app_root = app.xml()
            except etree.XMLSyntaxError:
                app_root = None
            if app_root is not None:
                company = app_root.find(
                    ".//{http://schemas.openxmlformats.org/officeDocument/2006/extended-properties}Company"
                )
                if company is not None and company.text:
                    doc.metadata.setdefault("core_properties", {})["company"] = company.text.strip()
                    if not doc.authority:
                        doc.authority = company.text.strip()

    def _parse_metadata_element(self, elem: etree._Element) -> EasaMetadata:
        """Parse a single metadata element (fixture-style nested XML)."""
        meta = EasaMetadata()

        erules_id_elem = elem.find(f".//{{{ERULES}}}id")
        if erules_id_elem is None:
            erules_id_elem = elem.find(f".//{{{ERULES_EXPORT}}}id")
        if erules_id_elem is not None:
            meta.erules_id = erules_id_elem.text or ""

        title_elem = elem.find(f".//{{{ERULES}}}title")
        if title_elem is None:
            title_elem = elem.find(f".//{{{ERULES_EXPORT}}}title")
        if title_elem is not None:
            meta.source_title = title_elem.text or ""

        field_map = {
            "regulatorySource": "regulatory_source",
            "regulatorySubject": "regulatory_subject",
            "typeOfContent": "type_of_content",
            "technicalSubjectMatter": "technical_subject_matter",
            "aircraftCategory": "aircraft_category",
            "aircraftUse": "aircraft_use",
            "amendedBy": "amended_by",
        }
        for xml_name, attr in field_map.items():
            values: list[str] = []
            for ns in (ERULES, ERULES_EXPORT):
                for node in elem.findall(f".//{{{ns}}}{xml_name}"):
                    if node.text:
                        values.append(node.text)
            if values:
                setattr(meta, attr, values)

        for ns in (ERULES, ERULES_EXPORT):
            app_date = elem.find(f".//{{{ns}}}applicabilityDate")
            if app_date is not None and app_date.text:
                meta.applicability_date = app_date.text
                break

        for child in elem:
            if not isinstance(child.tag, str):
                continue
            tag = etree.QName(child.tag).localname
            if child.text:
                meta.raw_attributes[tag] = child.text

        return meta

    def parse_nested(self, elem: etree._Element, parent: Any) -> None:
        """Parse nested metadata (e.g., within a topic)."""
        meta = self._parse_metadata_element(elem)
        if hasattr(parent, "metadata"):
            parent.metadata["easa"] = meta.to_dict()
