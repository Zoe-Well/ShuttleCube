from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import current_session, require_csrf
from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.attachments import (
    delete_attachment,
    list_attachments,
    upload_attachment,
)
from shuttlecube.config import Settings, get_settings
from shuttlecube.domain.finance.models import Attachment
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.infrastructure.artifacts.base import ObjectStorage
from shuttlecube.infrastructure.artifacts.factory import create_object_storage
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["Finance"])


class AttachmentDeleteWrite(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def get_artifact_store(settings: Annotated[Settings, Depends(get_settings)]) -> ObjectStorage:
    return create_object_storage(settings)


def attachment_dict(item: Attachment) -> dict[str, object]:
    return {
        "id": item.id,
        "owner_type": item.owner_type,
        "owner_id": item.owner_id,
        "original_filename": item.original_filename,
        "media_type": item.media_type,
        "size_bytes": item.size_bytes,
        "uploaded_at": item.uploaded_at,
        "status": item.status,
    }


@router.get("/attachments")
def get_attachments(
    owner_type: str,
    owner_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    return [attachment_dict(item) for item in list_attachments(db, owner_type, owner_id)]


@router.post("/attachments", status_code=201)
async def post_attachment(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
    storage: Annotated[ObjectStorage, Depends(get_artifact_store)],
    owner_type: Annotated[str, Form()],
    owner_id: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
) -> dict[str, object]:
    content = await file.read()
    item = upload_attachment(
        db,
        storage,
        owner_type=owner_type,
        owner_id=owner_id,
        original_filename=file.filename or "attachment",
        media_type=file.content_type or "application/octet-stream",
        content=content,
        actor_id=user.id,
        request_id=str(getattr(request.state, "request_id", "unknown")),
    )
    return attachment_dict(item)


@router.get("/attachments/{attachment_id}/content")
def get_attachment_content(
    attachment_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
    storage: Annotated[ObjectStorage, Depends(get_artifact_store)],
) -> Response:
    item = db.get(Attachment, attachment_id)
    if item is None or item.status != "active":
        raise BusinessError(404, "attachment_not_found", "凭证不存在")
    content, media_type = storage.get(item.storage_key)
    return Response(
        content,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{item.original_filename}"'},
    )


@router.delete("/attachments/{attachment_id}", status_code=204)
def remove_attachment(
    attachment_id: str,
    payload: AttachmentDeleteWrite,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[SystemUser, Depends(require_csrf)],
) -> Response:
    item = db.get(Attachment, attachment_id)
    if item is None:
        raise BusinessError(404, "attachment_not_found", "凭证不存在")
    delete_attachment(
        db,
        item,
        actor_id=user.id,
        reason=payload.reason,
        request_id=str(getattr(request.state, "request_id", "unknown")),
    )
    return Response(status_code=204)
