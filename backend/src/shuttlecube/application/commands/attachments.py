from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.domain.finance.attachment_policy import validate_attachment
from shuttlecube.domain.finance.models import Attachment, Expense, Payment, Refund
from shuttlecube.infrastructure.artifacts.base import ObjectStorage
from shuttlecube.infrastructure.database.base import utc_now


def _owner_exists(db: Session, owner_type: str, owner_id: str) -> bool:
    model = {"payment": Payment, "refund": Refund, "expense": Expense}.get(owner_type)
    if model is not None:
        return db.get(model, owner_id) is not None
    if owner_type == "payroll_settlement":
        from shuttlecube.domain.payroll.models import PayrollSettlement

        return db.get(PayrollSettlement, owner_id) is not None
    return False


def upload_attachment(
    db: Session,
    storage: ObjectStorage,
    *,
    owner_type: str,
    owner_id: str,
    original_filename: str,
    media_type: str,
    content: bytes,
    actor_id: str,
    request_id: str,
) -> Attachment:
    validate_attachment(media_type, len(content))
    if not _owner_exists(db, owner_type, owner_id):
        raise BusinessError(404, "attachment_owner_not_found", "凭证关联的业务记录不存在")
    stored = storage.put(content, media_type)
    item = Attachment(
        owner_type=owner_type,
        owner_id=owner_id,
        storage_key=stored.key,
        original_filename=original_filename,
        media_type=media_type,
        size_bytes=stored.size,
        uploaded_by=actor_id,
    )
    db.add(item)
    db.flush()
    record_audit(
        db,
        actor_id=actor_id,
        action="attachment.uploaded",
        entity_type=owner_type,
        entity_id=owner_id,
        request_id=request_id,
        after={
            "attachment_id": item.id,
            "filename": original_filename,
            "media_type": media_type,
            "size_bytes": stored.size,
        },
    )
    db.commit()
    return item


def list_attachments(db: Session, owner_type: str, owner_id: str) -> list[Attachment]:
    return list(
        db.scalars(
            select(Attachment)
            .where(
                Attachment.owner_type == owner_type,
                Attachment.owner_id == owner_id,
                Attachment.status == "active",
            )
            .order_by(Attachment.uploaded_at.desc())
        ).all()
    )


def delete_attachment(
    db: Session,
    item: Attachment,
    *,
    actor_id: str,
    reason: str,
    request_id: str,
) -> Attachment:
    if item.status != "active":
        return item
    item.status = "deleted"
    item.deleted_by = actor_id
    item.deleted_at = utc_now()
    record_audit(
        db,
        actor_id=actor_id,
        action="attachment.deleted",
        entity_type=item.owner_type,
        entity_id=item.owner_id,
        request_id=request_id,
        before={"attachment_id": item.id, "status": "active"},
        after={"attachment_id": item.id, "status": "deleted"},
        reason=reason,
    )
    db.commit()
    return item
