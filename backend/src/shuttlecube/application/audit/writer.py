from sqlalchemy.orm import Session

from shuttlecube.domain.audit.models import AuditLog


def record_audit(
    db: Session,
    *,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    request_id: str,
    before: dict[str, object] | None = None,
    after: dict[str, object] | None = None,
    reason: str | None = None,
    organization_id: str | None = None,
    venue_id: str | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_id,
            action_type=action,
            entity_type=entity_type,
            entity_id=entity_id,
            request_id=request_id,
            before_summary=before,
            after_summary=after,
            reason=reason,
            organization_id=organization_id,
            venue_id=venue_id,
        )
    )
