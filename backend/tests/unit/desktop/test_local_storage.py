from pathlib import Path

import pytest

from shuttlecube.infrastructure.artifacts.local import LocalObjectStorage


def test_local_storage_keeps_content_and_media_type(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "attachments")
    stored = storage.put(b"receipt", "image/png")

    assert stored.key.startswith("attachments/")
    assert stored.size == 7
    assert storage.get(stored.key) == (b"receipt", "image/png")


def test_local_storage_rejects_unsafe_keys(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path)
    with pytest.raises(ValueError):
        storage.get("../secret")
