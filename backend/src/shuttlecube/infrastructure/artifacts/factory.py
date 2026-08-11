from shuttlecube.config import Settings
from shuttlecube.infrastructure.artifacts.base import ObjectStorage
from shuttlecube.infrastructure.artifacts.local import LocalObjectStorage
from shuttlecube.infrastructure.artifacts.s3 import PrivateObjectStorage


def create_object_storage(settings: Settings) -> ObjectStorage:
    if settings.artifact_storage == "local":
        if settings.local_artifact_dir is None:
            raise ValueError("local_artifact_dir is required for local artifact storage")
        return LocalObjectStorage(settings.local_artifact_dir)
    return PrivateObjectStorage(settings)
