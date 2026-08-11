from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.domain.audit.models import AuditLog


def search_audit(
    db: Session,
    *,
    actor_id: str | None = None,
    action_type: str | None = None,
    entity_type: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = 200,
) -> list[AuditLog]:
    statement = select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(min(limit, 500))
    if actor_id:
        statement = statement.where(AuditLog.actor_user_id == actor_id)
    if action_type:
        statement = statement.where(AuditLog.action_type == action_type)
    if entity_type:
        statement = statement.where(AuditLog.entity_type == entity_type)
    if occurred_from:
        statement = statement.where(AuditLog.occurred_at >= occurred_from)
    if occurred_to:
        statement = statement.where(AuditLog.occurred_at <= occurred_to)
    return list(db.scalars(statement).all())


def entity_history(db: Session, entity_type: str, entity_id: str) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
            .order_by(AuditLog.occurred_at.desc())
        ).all()
    )


def request_trace(db: Session, request_id: str) -> list[AuditLog]:
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.request_id == request_id)
            .order_by(AuditLog.occurred_at.asc())
        ).all()
    )
