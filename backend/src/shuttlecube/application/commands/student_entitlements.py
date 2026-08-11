from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.audit.writer import record_audit
from shuttlecube.application.commands.attendance import balance
from shuttlecube.application.queries.receivables import receivable_for_source, receivable_summary
from shuttlecube.domain.classes.enrollment_models import Enrollment, LessonUnitLedger
from shuttlecube.domain.private_lessons.models import PrivateLessonPackage
from shuttlecube.infrastructure.database.base import utc_now


def terminate_student_entitlement(
    db: Session,
    *,
    student_id: str,
    entitlement_type: str,
    entitlement_id: str,
    version: int,
    reason: str,
    actor_id: str,
    request_id: str,
) -> Enrollment | PrivateLessonPackage:
    item: Enrollment | PrivateLessonPackage | None
    if entitlement_type == "fixed_class":
        item = db.get(Enrollment, entitlement_id)
        source_type = "enrollment"
        next_status = "cancelled"
    elif entitlement_type == "private_package":
        item = db.get(PrivateLessonPackage, entitlement_id)
        source_type = "private_package"
        next_status = "void"
    else:
        raise BusinessError(422, "invalid_entitlement_type", "不支持的培训权益类型")
    if item is None or item.student_id != student_id:
        raise BusinessError(404, "entitlement_not_found", "培训权益不存在")
    if item.version != version:
        raise BusinessError(409, "concurrent_change", "培训权益已经发生变化")
    if item.status in {"cancelled", "void", "refunded", "terminated"}:
        return item
    receivable = receivable_for_source(db, source_type, item.id)
    if receivable is not None:
        summary = receivable_summary(db, receivable)
        if summary.refundable_amount > 0:
            raise BusinessError(
                409, "entitlement_refund_required", "该权益已有实收，请先在财务中完成退款"
            )
        receivable.status = "void"
    current_balance = balance(db, item.id)
    if current_balance > 0:
        db.add(
            LessonUnitLedger(
                owner_type="enrollment" if entitlement_type == "fixed_class" else "private_package",
                owner_id=item.id,
                change_type="correction",
                delta=-current_balance,
                balance_before=current_balance,
                balance_after=0,
                source_type="entitlement_termination",
                source_id=item.id,
                reason=reason,
                operated_by=actor_id,
                operated_at=utc_now(),
                idempotency_key=f"terminate-entitlement:{item.id}:{item.version}",
            )
        )
    before = {"status": item.status, "remaining_units": current_balance}
    item.status = next_status
    record_audit(
        db,
        actor_id=actor_id,
        action="student.entitlement_terminated",
        entity_type=source_type,
        entity_id=item.id,
        request_id=request_id,
        before=before,
        after={"status": next_status, "remaining_units": 0},
        reason=reason,
    )
    db.commit()
    return item
