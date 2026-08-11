from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    checksum: str
    size: int


class ObjectStorage(Protocol):
    def put(self, content: bytes, media_type: str) -> StoredObject: ...

    def get(self, key: str) -> tuple[bytes, str]: ...
