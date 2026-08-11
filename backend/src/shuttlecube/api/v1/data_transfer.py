from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from shuttlecube.api.dependencies import current_session, require_csrf
from shuttlecube.api.errors import BusinessError
from shuttlecube.config import Settings, get_settings
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.infrastructure.desktop.paths import DesktopDataPaths
from shuttlecube.infrastructure.desktop.transfer import (
    TransferError,
    directory_size,
    export_transfer,
    stage_import,
    validate_transfer,
)

router = APIRouter(prefix="/data-transfer", tags=["Data transfer"])


class DataTransferStatus(BaseModel):
    desktop_mode: bool
    data_directory: str | None
    database_size_bytes: int
    attachment_size_bytes: int
    pending_import: bool


class FolderInput(BaseModel):
    path: str = Field(min_length=1, max_length=2048)


class ExportResult(BaseModel):
    path: str


class ImportResult(BaseModel):
    app_version: str
    schema_version: str
    exported_at: str
    restart_required: bool = True


def _desktop_paths(settings: Settings) -> DesktopDataPaths:
    if not settings.desktop_mode or settings.data_dir is None:
        raise BusinessError(409, "desktop_only", "数据文件夹迁移仅在单机桌面版中可用")
    return DesktopDataPaths.from_root(settings.data_dir)


@router.get("/status", response_model=DataTransferStatus)
def transfer_status(
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> DataTransferStatus:
    if not settings.desktop_mode or settings.data_dir is None:
        return DataTransferStatus(
            desktop_mode=False,
            data_directory=None,
            database_size_bytes=0,
            attachment_size_bytes=0,
            pending_import=False,
        )
    paths = DesktopDataPaths.from_root(settings.data_dir)
    return DataTransferStatus(
        desktop_mode=True,
        data_directory=str(paths.root),
        database_size_bytes=paths.database.stat().st_size if paths.database.is_file() else 0,
        attachment_size_bytes=directory_size(paths.attachments),
        pending_import=paths.pending_import.is_dir(),
    )


@router.post("/export", response_model=ExportResult)
def export_data(
    payload: FolderInput,
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> ExportResult:
    paths = _desktop_paths(settings)
    try:
        destination = export_transfer(paths, Path(payload.path))
    except (OSError, TransferError) as exc:
        raise BusinessError(422, "export_failed", str(exc)) from exc
    return ExportResult(path=str(destination))


@router.post("/validate", response_model=ImportResult)
def validate_data(
    payload: FolderInput,
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> ImportResult:
    _desktop_paths(settings)
    try:
        manifest = validate_transfer(Path(payload.path))
    except (OSError, TransferError) as exc:
        raise BusinessError(422, "invalid_transfer", str(exc)) from exc
    return ImportResult(
        app_version=manifest.app_version,
        schema_version=manifest.schema_version,
        exported_at=manifest.exported_at,
    )


@router.post("/import", response_model=ImportResult)
def import_data(
    payload: FolderInput,
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[SystemUser, Depends(require_csrf)],
) -> ImportResult:
    paths = _desktop_paths(settings)
    try:
        manifest = stage_import(paths, Path(payload.path))
    except (OSError, TransferError) as exc:
        raise BusinessError(422, "import_failed", str(exc)) from exc
    return ImportResult(
        app_version=manifest.app_version,
        schema_version=manifest.schema_version,
        exported_at=manifest.exported_at,
    )
