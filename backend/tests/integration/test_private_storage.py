import hashlib
from io import BytesIO

from shuttlecube.config import Settings
from shuttlecube.infrastructure.artifacts.s3 import PrivateObjectStorage


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        self.objects[(Bucket, Key)] = (Body, ContentType)

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        content, media_type = self.objects[(Bucket, Key)]
        return {"Body": BytesIO(content), "ContentType": media_type}


def test_private_object_round_trip_and_checksum(monkeypatch) -> None:
    fake = FakeS3()
    monkeypatch.setattr(
        "shuttlecube.infrastructure.artifacts.s3.boto3.client", lambda *_a, **_k: fake
    )
    storage = PrivateObjectStorage(Settings())
    content = b"private receipt"

    stored = storage.put(content, "image/png")

    assert stored.key.startswith("attachments/")
    assert stored.checksum == hashlib.sha256(content).hexdigest()
    assert storage.get(stored.key) == (content, "image/png")
