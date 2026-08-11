from sqlalchemy.orm import Session

from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.queries.audit import entity_history, request_trace, search_audit


def test_audit_can_be_queried_by_entity_actor_and_request(db: Session, admin) -> None:
    record_audit(
        db,
        actor_id=admin.id,
        action="receivable.adjusted",
        entity_type="receivable",
        entity_id="receivable-1",
        request_id="request-1",
        before={"actual_amount": "100.00"},
        after={"actual_amount": "80.00"},
        reason="优惠调整",
    )
    db.commit()
    assert len(entity_history(db, "receivable", "receivable-1")) == 1
    assert len(request_trace(db, "request-1")) == 1
    assert len(search_audit(db, actor_id=admin.id, action_type="receivable.adjusted")) == 1

