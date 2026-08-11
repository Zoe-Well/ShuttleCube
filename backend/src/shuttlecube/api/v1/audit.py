from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import current_session
from shuttlecube.application.queries.audit import entity_history, request_trace, search_audit
from shuttlecube.application.queries.business_display import (
    audit_action_label,
    audit_business_summary,
    audit_change_items,
    audit_entity_label,
    audit_entity_name,
)
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.infrastructure.database.session import get_db

router = APIRouter(tags=["Audit"])


def audit_dict(db: Session, item: AuditLog) -> dict[str, object]:
    actor = db.get(SystemUser, item.actor_user_id)
    return {
        "id": item.id,
        "actor_user_id": item.actor_user_id,
        "actor_name": actor.display_name if actor else item.actor_user_id,
        "action_type": item.action_type,
        "action_label": audit_action_label(item.action_type),
        "entity_type": item.entity_type,
        "entity_id": item.entity_id,
        "entity_label": audit_entity_label(item.entity_type),
        "entity_name": audit_entity_name(db, item.entity_type, item.entity_id),
        "occurred_at": item.occurred_at,
        "before_summary": item.before_summary,
        "after_summary": item.after_summary,
        "business_summary": audit_business_summary(item.before_summary, item.after_summary),
        "changes": audit_change_items(item.before_summary, item.after_summary),
        "is_noop": (
            item.before_summary is not None
            and item.after_summary is not None
            and item.before_summary == item.after_summary
        ),
        "reason": item.reason,
        "request_id": item.request_id,
    }


@router.get("/audit")
def get_audit(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
    actor_id: str | None = None,
    action_type: str | None = None,
    entity_type: str | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = 200,
) -> list[dict[str, object]]:
    return [
        audit_dict(db, item)
        for item in search_audit(
            db,
            actor_id=actor_id,
            action_type=action_type,
            entity_type=entity_type,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            limit=limit,
        )
    ]


@router.get("/audit/entities/{entity_type}/{entity_id}")
def get_entity_audit(
    entity_type: str,
    entity_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    return [audit_dict(db, item) for item in entity_history(db, entity_type, entity_id)]


@router.get("/audit/requests/{request_id}")
def get_request_audit(
    request_id: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[tuple[object, object], Depends(current_session)],
) -> list[dict[str, object]]:
    return [audit_dict(db, item) for item in request_trace(db, request_id)]
