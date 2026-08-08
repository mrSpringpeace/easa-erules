"""Assets (images, media) model."""

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Asset:
    """Represents an extracted asset (image, etc.)."""
    original_path: str  # Original path in OOXML package (e.g., word/media/image1.png)
    content_type: str  # MIME type
    data: bytes  # Binary data
    deterministic_name: str = ""  # Deterministic filename (e.g., cs-vla-441-fig-01.png)
    width: int | None = None
    height: int | None = None
    relationship_id: str = ""  # OOXML relationship ID

    def __post_init__(self):
        if not self.deterministic_name:
            # Generate from hash if not provided
            self.deterministic_name = self._generate_name()

    def _generate_name(self) -> str:
        """Generate deterministic name from content hash."""
        hash_suffix = hashlib.sha256(self.data).hexdigest()[:8]
        ext = self.content_type.split("/")[-1]
        if ext == "jpeg":
            ext = "jpg"
        return f"asset-{hash_suffix}.{ext}"

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def size(self) -> int:
        return len(self.data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_path": self.original_path,
            "content_type": self.content_type,
            "deterministic_name": self.deterministic_name,
            "width": self.width,
            "height": self.height,
            "relationship_id": self.relationship_id,
            "sha256": self.sha256,
            "size": self.size,
        }


@dataclass(slots=True)
class AssetCollection:
    """Collection of all assets in a document."""
    assets: dict[str, Asset] = field(default_factory=dict)  # key = deterministic_name

    def add(self, asset: Asset) -> Asset:
        # Handle name collisions
        name = asset.deterministic_name
        counter = 1
        base_name = name
        while name in self.assets:
            if self.assets[name].sha256 == asset.sha256:
                # Same content, reuse
                return self.assets[name]
            # Different content, modify name
            name = f"{base_name.rsplit('.', 1)[0]}-{counter}.{base_name.rsplit('.', 1)[1]}"
            counter += 1
        asset.deterministic_name = name
        self.assets[name] = asset
        return asset

    def get(self, name: str) -> Asset | None:
        return self.assets.get(name)

    def find_by_relationship_id(self, rel_id: str) -> Asset | None:
        for asset in self.assets.values():
            if asset.relationship_id == rel_id:
                return asset
        return None

    def to_dict(self) -> dict[str, Any]:
        return {name: asset.to_dict() for name, asset in self.assets.items()}