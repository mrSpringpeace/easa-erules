"""Flat OPC / OOXML Package reader."""

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from .namespaces import CT, FLAT_OPC, REL
from .relationships import Relationship, Relationships, RelTypes


@dataclass(slots=True)
class PackagePart:
    """Represents a part in the OOXML package."""
    path: str
    content_type: str
    data: bytes
    relationships: Relationships | None = None

    def xml(self) -> etree._Element:
        """Parse part as XML."""
        return etree.fromstring(self.data)

    def text(self, encoding: str = "utf-8") -> str:
        """Get part as text."""
        return self.data.decode(encoding)


def _normalize_part_path(path: str) -> str:
    """Normalize a package part path (no leading slash, forward slashes)."""
    return path.replace("\\", "/").lstrip("/")


def rels_path_for_part(part_path: str) -> str:
    """Return the OPC relationships part path for a given part.

    ``word/document.xml`` -> ``word/_rels/document.xml.rels``
    """
    part_path = _normalize_part_path(part_path)
    directory = os.path.dirname(part_path)
    basename = os.path.basename(part_path)
    if directory:
        return f"{directory}/_rels/{basename}.rels"
    return f"_rels/{basename}.rels"


class OpcPackage:
    """
    Flat OPC / OOXML Package reader.

    Handles both .docx (ZIP) and Flat OPC (.xml) formats.
    Provides abstraction over physical storage (ZIP vs flat XML).
    """

    def __init__(self):
        self._parts: dict[str, PackagePart] = {}
        self._content_types: dict[str, str] = {}  # extension/override -> content-type
        self._default_content_types: dict[str, str] = {}  # extension -> content-type
        self._package_relationships = Relationships()

    @classmethod
    def from_file(cls, path: str | Path) -> "OpcPackage":
        """Load package from file (ZIP or Flat OPC XML)."""
        path = Path(path)
        if path.suffix.lower() == ".xml":
            return cls._from_flat_opc(path)
        else:
            return cls._from_zip(path)

    @classmethod
    def from_bytes(cls, data: bytes) -> "OpcPackage":
        """Load package from bytes (auto-detect format)."""
        if data.startswith(b"<?xml") or data.startswith(b"<pkg:package"):
            return cls._from_flat_opc_bytes(data)
        else:
            return cls._from_zip_bytes(data)

    @classmethod
    def _from_zip(cls, path: Path) -> "OpcPackage":
        pkg = cls()
        with zipfile.ZipFile(path, "r") as zf:
            # Read [Content_Types].xml first
            try:
                ct_data = zf.read("[Content_Types].xml")
                pkg._parse_content_types(ct_data)
            except KeyError:
                pass

            # Read all parts
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                data = zf.read(name)
                content_type = pkg._guess_content_type(name)
                part = PackagePart(path=name, content_type=content_type, data=data)
                pkg._parts[name] = part

            # Load relationships for each part
            pkg._load_relationships_from_zip(zf)

        return pkg

    @classmethod
    def _from_zip_bytes(cls, data: bytes) -> "OpcPackage":
        import io
        pkg = cls()
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            try:
                ct_data = zf.read("[Content_Types].xml")
                pkg._parse_content_types(ct_data)
            except KeyError:
                pass

            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                part_data = zf.read(name)
                content_type = pkg._guess_content_type(name)
                part = PackagePart(path=name, content_type=content_type, data=part_data)
                pkg._parts[name] = part

            pkg._load_relationships_from_zip(zf)

        return pkg

    @classmethod
    def _from_flat_opc(cls, path: Path) -> "OpcPackage":
        with open(path, "rb") as f:
            data = f.read()
        return cls._from_flat_opc_bytes(data)

    @classmethod
    def _from_flat_opc_bytes(cls, data: bytes) -> "OpcPackage":
        pkg = cls()
        root = etree.fromstring(data)

        # Parse content types from package
        ct_elem = root.find(f".//{{{CT}}}Types")
        if ct_elem is not None:
            pkg._parse_content_types(etree.tostring(ct_elem))

        # Parse parts (Flat OPC uses pkg:part in Microsoft namespace)
        for part_elem in root.findall(f".//{{{FLAT_OPC}}}part"):
            pkg._parse_flat_opc_part(part_elem)

        # Associate .rels parts with their main parts (e.g., word/_rels/document.xml.rels -> word/document.xml)
        pkg._associate_rels_parts()

        # Load package-level relationships
        pkg._load_package_relationships_flat_opc(root)

        return pkg

    def _associate_rels_parts(self) -> None:
        """Associate .rels parts with their corresponding main parts."""
        for name, part in list(self._parts.items()):
            if name.endswith(".rels"):
                # This is a relationships part, find the corresponding main part
                # e.g., word/_rels/document.xml.rels -> word/document.xml
                # e.g., word/document.xml.rels -> word/document.xml
                rels_name = name[:-5]  # Remove .rels
                if "/_rels/" in rels_name:
                    # Handle word/_rels/document.xml -> word/document.xml
                    main_part_name = rels_name.replace("/_rels/", "/")
                else:
                    main_part_name = rels_name
                
                if main_part_name in self._parts:
                    main_part = self._parts[main_part_name]
                    main_part.relationships = part.relationships

    def _load_package_relationships_flat_opc(self, root: etree._Element) -> None:
        """Load package-level relationships from Flat OPC."""
        # Find the _rels/.rels part (with or without leading slash)
        for part_elem in root.findall(f".//{{{FLAT_OPC}}}part"):
            name = part_elem.get(f"{{{FLAT_OPC}}}name", "")
            if name.lstrip("/") == "_rels/.rels":
                xml_data = part_elem.find(f".//{{{FLAT_OPC}}}xmlData")
                if xml_data is not None and len(xml_data) > 0:
                    rels_data = etree.tostring(xml_data[0], encoding="utf-8")
                    self._package_relationships = Relationships.from_xml(rels_data)
                    return

        # Also check for Relationships element directly in package
        rels_elem = root.find(f".//{{{REL}}}Relationships")
        if rels_elem is not None:
            rels_data = etree.tostring(rels_elem, encoding="utf-8")
            self._package_relationships = Relationships.from_xml(rels_data)
        else:
            self._package_relationships = Relationships()

    def _parse_content_types(self, ct_data: bytes) -> None:
        root = etree.fromstring(ct_data)
        for default in root.findall(f".//{{{CT}}}Default"):
            ext = default.get("Extension")
            ct = default.get("ContentType")
            if ext and ct:
                self._default_content_types[ext.lower()] = ct

        for override in root.findall(f".//{{{CT}}}Override"):
            part_name = override.get("PartName")
            ct = override.get("ContentType")
            if part_name and ct:
                self._content_types[part_name.lstrip("/")] = ct

    def _guess_content_type(self, part_name: str) -> str:
        # Check override first
        if part_name in self._content_types:
            return self._content_types[part_name]

        # Check default by extension
        ext = Path(part_name).suffix.lower().lstrip(".")
        if ext in self._default_content_types:
            return self._default_content_types[ext]

        # Fallback guesses
        if part_name.endswith(".xml"):
            return "application/xml"
        if part_name.endswith(".rels"):
            return "application/vnd.openxmlformats-package.relationships+xml"
        if part_name.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff")):
            return f"image/{ext}"
        return "application/octet-stream"

    def _parse_flat_opc_part(self, part_elem: etree._Element) -> None:
        """Parse a single part from Flat OPC XML."""
        name = part_elem.get(f"{{{FLAT_OPC}}}name", "").lstrip("/")
        content_type = part_elem.get(f"{{{FLAT_OPC}}}contentType", "application/xml")

        # Get part data - could be XML or base64 encoded binary
        xml_data_elem = part_elem.find(f".//{{{FLAT_OPC}}}xmlData")
        binary_data_elem = part_elem.find(f".//{{{FLAT_OPC}}}binaryData")

        if xml_data_elem is not None:
            # XML part - serialize the child element
            if len(xml_data_elem) > 0:
                data = etree.tostring(xml_data_elem[0], encoding="utf-8", xml_declaration=True)
            else:
                data = b""
        elif binary_data_elem is not None:
            # Binary part - base64 decode
            import base64
            data = base64.b64decode(binary_data_elem.text or "")
        else:
            data = b""

        part = PackagePart(path=name, content_type=content_type, data=data)
        self._parts[name] = part

        # Check for relationships in the part's xmlData
        xml_data_elem = part_elem.find(f".//{{{FLAT_OPC}}}xmlData")
        if xml_data_elem is not None and len(xml_data_elem) > 0:
            # Check if the first child is a Relationships element
            first_child = xml_data_elem[0]
            if first_child.tag.endswith("}Relationships"):
                rels_data = etree.tostring(first_child, encoding="utf-8")
                part.relationships = Relationships.from_xml(rels_data)

        # Also check for relationships element directly in the part (fallback)
        rels_elem = part_elem.find(f".//{{{FLAT_OPC}}}relationships")
        if rels_elem is not None:
            rels_data = etree.tostring(rels_elem, encoding="utf-8")
            part.relationships = Relationships.from_xml(rels_data)

    def _load_relationships_from_zip(self, zf: zipfile.ZipFile) -> None:
        """Load .rels files for all parts using OPC path conventions."""
        names = set(zf.namelist())

        for part_name in list(self._parts.keys()):
            if part_name.endswith(".rels"):
                continue

            # OPC standard: word/_rels/document.xml.rels for word/document.xml
            candidates = [
                rels_path_for_part(part_name),
                f"{part_name}.rels",  # rare non-standard layout
            ]
            for rels_name in candidates:
                if rels_name in names:
                    rels_data = zf.read(rels_name)
                    self._parts[part_name].relationships = Relationships.from_xml(rels_data)
                    break

        # Package-level relationships
        if "_rels/.rels" in names:
            rels_data = zf.read("_rels/.rels")
            self._package_relationships = Relationships.from_xml(rels_data)
        else:
            self._package_relationships = Relationships()

    def get_part(self, path: str, base_path: str = "") -> PackagePart | None:
        """Get a part by its path (e.g., 'word/document.xml').

        If ``base_path`` is given, also try resolving ``path`` relative to it
        (source part directory and its ``_rels`` directory).
        """
        return self.resolve_part(path, source_part_path=base_path)

    def resolve_part(self, target: str, source_part_path: str = "") -> PackagePart | None:
        """Resolve a relationship target to a package part.

        Tries absolute package paths and relative resolution against the
        source part directory (OPC) and the relationships directory
        (some producers use ``../media/...`` relative to ``_rels``).
        """
        target = _normalize_part_path(target)
        candidates: list[str] = [target]

        if source_part_path:
            source = _normalize_part_path(source_part_path)
            # If base is a .rels path, treat its parent package part dir correctly
            if source.endswith(".rels"):
                # word/_rels/document.xml.rels -> source part dir is word/
                rels_dir = os.path.dirname(source)  # word/_rels
                source_dir = os.path.dirname(rels_dir) if rels_dir.endswith("_rels") else rels_dir
                candidates.append(_normalize_part_path(os.path.normpath(os.path.join(rels_dir, target))))
                candidates.append(_normalize_part_path(os.path.normpath(os.path.join(source_dir, target))))
            else:
                source_dir = os.path.dirname(source)
                candidates.append(
                    _normalize_part_path(os.path.normpath(os.path.join(source_dir, target)))
                )
                rels_dir = f"{source_dir}/_rels" if source_dir else "_rels"
                candidates.append(
                    _normalize_part_path(os.path.normpath(os.path.join(rels_dir, target)))
                )

        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            part = self._parts.get(candidate)
            if part is not None:
                return part
        return None

    def get_relationship(self, rel_id: str) -> Relationship | None:
        """Get relationship by ID from package-level relationships."""
        return self._package_relationships.get(rel_id)

    def get_binary(self, path: str) -> bytes | None:
        """Get binary content of a part."""
        part = self.get_part(path)
        return part.data if part else None

    def get_xml(self, path: str) -> etree._Element | None:
        """Get parsed XML of a part."""
        part = self.get_part(path)
        return part.xml() if part else None

    def get_main_document_part(self) -> PackagePart | None:
        """Get the main document part (word/document.xml)."""
        # Try package relationships first
        for rel in self._package_relationships.find_by_type(RelTypes.OFFICE_DOCUMENT):
            return self.get_part(rel.target)

        # Fallback to standard location
        return self.get_part("word/document.xml")

    def get_styles_part(self) -> PackagePart | None:
        """Get styles.xml part."""
        for rel in self._package_relationships.find_by_type(RelTypes.STYLES):
            return self.get_part(rel.target)
        return self.get_part("word/styles.xml")

    def get_numbering_part(self) -> PackagePart | None:
        """Get numbering.xml part."""
        for rel in self._package_relationships.find_by_type(RelTypes.NUMBERING):
            return self.get_part(rel.target)
        return self.get_part("word/numbering.xml")

    def get_media_parts(self) -> dict[str, PackagePart]:
        """Get all media parts (images)."""
        return {
            name: part
            for name, part in self._parts.items()
            if part.content_type.startswith("image/")
        }

    def get_all_parts(self) -> dict[str, PackagePart]:
        return self._parts.copy()

    def iter_parts(self):
        return iter(self._parts.values())

    def __contains__(self, path: str) -> bool:
        return path in self._parts

    def __len__(self) -> int:
        return len(self._parts)