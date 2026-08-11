import hashlib
from uuid import uuid4

import boto3

from shuttlecube.config import Settings
from shuttlecube.infrastructure.artifacts.base import StoredObject


class PrivateObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name="us-east-1",
        )

    def put(self, content: bytes, media_type: str) -> StoredObject:
        key = f"attachments/{uuid4()}"
        checksum = hashlib.sha256(content).hexdigest()
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content, ContentType=media_type)
        return StoredObject(key=key, checksum=checksum, size=len(content))

    def get(self, key: str) -> tuple[bytes, str]:
        result = self.client.get_object(Bucket=self.bucket, Key=key)
        return result["Body"].read(), result.get("ContentType", "application/octet-stream")
