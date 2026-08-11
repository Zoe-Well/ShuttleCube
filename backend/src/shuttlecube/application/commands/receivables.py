from decimal import Decimal

from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.queries.receivables import (
    money,
    receivable_for_source,
    receivable_summary,
    sync_receivable_status,
)
from shuttlecube.domain.finance.models import Receivable


def create_receivable(
    db: Session,
    *,
    source_type: str,
    source_id: str,
    suggested_amount: Decimal,
    actual_amount: Decimal,
    adjustment_reason: str | None = None,
) -> Receivable:
    existing = receivable_for_source(db, source_type, source_id)
    if existing:
        return existing
    suggested = money(suggested_amount)
    actual = money(actual_amount)
    if actual < 0:
        raise BusinessError(422, "invalid_receivable_amount", "实际应收不得为负数")
    if suggested != actual and not adjustment_reason:
        raise BusinessError(422, "adjustment_reason_required", "调整实际应收必须填写原因")
    item = Receivable(
        source_type=source_type,
        source_id=source_id,
        suggested_amount=suggested,
        actual_amount=actual,
        adjustment_reason=adjustment_reason,
        status="settled" if actual == 0 else "open",
    )
    db.add(item)
    db.flush()
    return item


def adjust_receivable(
    db: Session,
    item: Receivable,
    *,
    actual_amount: Decimal,
    reason: str,
    actor_id: str,
    request_id: str,
) -> Receivable:
    next_amount = money(actual_amount)
    if next_amount < 0:
        raise BusinessError(422, "invalid_receivable_amount", "实际应收不得为负数")
    summary = receivable_summary(db, item)
    if next_amount < summary.net_received:
        raise BusinessError(422, "receivable_below_net_received", "实际应收不得低于当前净实收")
    before: dict[str, object] = {
        "actual_amount": str(item.actual_amount),
        "status": item.status,
    }
    item.actual_amount = next_amount
    item.adjustment_reason = reason
    sync_receivable_status(db, item)
    record_audit(
        db,
        actor_id=actor_id,
        action="receivable.adjusted",
        entity_type="receivable",
        entity_id=item.id,
        request_id=request_id,
        before=before,
        after={"actual_amount": str(item.actual_amount), "status": item.status},
        reason=reason,
    )
    db.commit()
    return item
