from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

from shuttlecube.infrastructure.artifacts.base import StoredObject


class LocalObjectStorage:
    """Private artifact storage rooted inside the desktop data directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes, media_type: str) -> StoredObject:
        object_id = uuid4()
        key = f"attachments/{object_id}"
        target = self.root / str(object_id)
        metadata = self.root / f"{object_id}.json"
        target.write_bytes(content)
        metadata.write_text(json.dumps({"media_type": media_type}), encoding="utf-8")
        return StoredObject(
            key=key,
            checksum=hashlib.sha256(content).hexdigest(),
            size=len(content),
        )

    def get(self, key: str) -> tuple[bytes, str]:
        object_id = self._object_id(key)
        target = self.root / str(object_id)
        metadata = self.root / f"{object_id}.json"
        media_type = "application/octet-stream"
        if metadata.is_file():
            media_type = str(json.loads(metadata.read_text(encoding="utf-8")).get("media_type"))
        return target.read_bytes(), media_type

    @staticmethod
    def _object_id(key: str) -> UUID:
        prefix, separator, value = key.partition("/")
        if prefix != "attachments" or not separator:
            raise ValueError("invalid local storage key")
        return UUID(value)
