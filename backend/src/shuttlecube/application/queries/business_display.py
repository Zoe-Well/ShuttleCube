from sqlalchemy.orm import Session

from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment
from shuttlecube.domain.customers.models import Student, WalkInCustomer
from shuttlecube.domain.events.models import TemporaryEvent
from shuttlecube.domain.finance.models import Expense, OtherIncome, Receivable
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.payroll.models import CoachFee, PayrollSettlement
from shuttlecube.domain.private_lessons.models import PrivateLesson, PrivateLessonPackage
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.domain.scheduling.models import ScheduleEntry
from shuttlecube.domain.venue_bookings.models import VenueBooking

SOURCE_LABELS = {
    "enrollment": "固定班",
    "private_package": "私教课包",
    "private_lesson": "单次私教",
    "venue_booking": "场地预订",
    "event": "临时活动",
    "other": "其他应收",
}

ACTION_LABELS = {
    "attachment.uploaded": "上传付款凭证",
    "attachment.deleted": "删除付款凭证",
    "expense.created": "登记经营支出",
    "expense.voided": "作废经营支出",
    "other_income.created": "登记其他收入",
    "other_income.voided": "作废其他收入",
    "payment.recorded": "登记收款",
    "payment.voided": "作废收款",
    "payroll.settled": "确认教练月结",
    "payroll.voided": "作废教练月结",
    "receivable.adjusted": "调整应收金额",
    "refund.recorded": "登记退款",
    "refund.voided": "作废退款",
    "student.entitlement_terminated": "终止学员培训权益",
    "event.deleted": "删除临时活动",
    "court.status_changed": "变更场地状态",
    "coach.updated": "修改教练资料",
    "coach.created": "新增教练",
    "coach_fee.adjusted": "调整教练费用",
    "coach.status_changed": "变更教练状态",
    "venue.business_hours_updated": "更新场馆营业时间",
    "venue.default_prices_updated": "更新场地默认价格",
    "schedule.created": "创建排期",
    "schedule.rescheduled": "调整排期",
    "schedule.deleted": "删除排期",
    "schedule.cancelled": "取消排期",
    "class_session.rescheduled": "调整固定班课次时间",
    "class_session.cancelled": "取消固定班课次",
    "class_session.replacement_scheduled": "安排固定班补排课次",
    "fixed_class.capacity_changed": "调整固定班容量",
    "fixed_class.renewed": "续期固定班",
    "fixed_class.archived": "结束固定班",
    "student.entitlement_renewed": "续期学员课时",
    "student.entitlement_transferred": "转移学员课时",
    "private_lesson.deleted": "删除私教课程",
    "venue_booking.deleted": "删除场地预订",
    "private_package.invalid_data_deleted": "清理错误私教课包",
    "data.cleanup": "历史错误数据清理",
}

ENTITY_LABELS = {
    "receivable": "应收业务",
    "expense": "经营支出",
    "other_income": "其他收入",
    "payroll_settlement": "教练结算",
    "student_entitlement": "培训权益",
    "enrollment": "固定班学员权益",
    "fixed_class": "固定班",
    "class_session": "固定班课次",
    "coach_fee": "教练费用",
    "event": "临时活动",
    "venue_booking": "场地预订",
    "private_lesson": "私教课程",
    "private_package": "私教课包",
    "schedule_entry": "排期记录",
    "schedule_source": "排期业务",
    "court": "场地",
    "coach": "教练",
    "venue": "场馆",
    "venue_price_rules": "场地价格",
    "attachment": "付款凭证",
    "system": "系统数据",
}

AUDIT_FIELD_LABELS = {
    "status": "状态",
    "name": "名称",
    "phone": "联系电话",
    "notes": "备注",
    "is_active": "是否启用",
    "capacity": "班级容量",
    "session_count": "课程总节数",
    "additional_sessions": "新增课次",
    "purchased_units": "购买课时",
    "remaining_units": "剩余课时",
    "suggested_receivable": "建议应收",
    "actual_receivable": "实际应收",
    "suggested_amount": "建议金额",
    "actual_amount": "实际金额",
    "received_amount": "累计收款",
    "refunded_amount": "累计退款",
    "net_received": "净收款",
    "outstanding_amount": "待收款",
    "refundable_amount": "可退款金额",
    "payment_status": "收款状态",
    "base_amount": "基础金额",
    "adjustment_amount": "调整金额",
    "calculated_amount": "计算金额",
    "fixed_class_fee": "固定班单节教练费",
    "fixed_class_fee_effective_from": "固定班教练费生效日期",
    "private_lesson_fee": "私教单节教练费",
    "scheduled_start": "开始时间",
    "scheduled_end": "结束时间",
    "starts_at": "开始时间",
    "ends_at": "结束时间",
    "category": "分类",
    "amount": "金额",
    "payee": "收款方",
    "payer": "付款方",
    "coach_name": "关联教练",
    "invalid_fixed_class_coaches": "无效固定班教练关联",
    "invalid_class_session_coaches": "无效课次教练关联",
    "invalid_coach_fees": "无效教练费用",
    "invalid_court_allocations": "无效场地关联",
    "expanded_court_allocations": "补全场地占用",
    "attendance": "考勤记录",
    "enrollments": "报名记录",
    "ledgers": "课时流水",
    "ledgers_deleted": "已清理课时流水",
    "receivables_deleted": "已清理应收记录",
    "deleted": "已删除",
    "periods": "价格时段",
    "weekday_open_time": "工作日开馆时间",
    "weekday_close_time": "工作日闭馆时间",
    "weekend_open_time": "周末开馆时间",
    "weekend_close_time": "周末闭馆时间",
}

AUDIT_VALUE_LABELS = {
    "active": "启用",
    "inactive": "停用",
    "confirmed": "已确认",
    "cancelled": "已取消",
    "completed": "已完成",
    "deleted": "已删除",
    "pending": "待处理",
    "voided": "已作废",
    "paid": "已结清",
    "partially_paid": "部分收款",
    "unpaid": "待收款",
}

AUDIT_HIDDEN_FIELDS = {
    "id",
    "version",
    "source_id",
    "student_id",
    "coach_id",
    "expense_id",
    "receivable_id",
    "settlement_id",
    "fee_ids",
    "renewed_enrollment_ids",
}


def _student_name(db: Session, student_id: str) -> str:
    student = db.get(Student, student_id)
    return student.name if student else student_id


def source_business_name(db: Session, source_type: str, source_id: str) -> str:
    label = SOURCE_LABELS.get(source_type, source_type)
    if source_type == "enrollment":
        enrollment = db.get(Enrollment, source_id)
        fixed_class = db.get(FixedClass, enrollment.fixed_class_id) if enrollment else None
        return (
            f"{label}-{fixed_class.name if fixed_class else '已删除班级'}-{_student_name(db, enrollment.student_id)}"
            if enrollment
            else f"{label}（已删除）"
        )
    if source_type == "private_package":
        package = db.get(PrivateLessonPackage, source_id)
        return (
            f"{label}-{_student_name(db, package.student_id)}" if package else f"{label}（已删除）"
        )
    if source_type == "private_lesson":
        lesson = db.get(PrivateLesson, source_id)
        return f"{label}-{_student_name(db, lesson.student_id)}" if lesson else f"{label}（已删除）"
    if source_type == "venue_booking":
        booking = db.get(VenueBooking, source_id)
        customer = db.get(WalkInCustomer, booking.customer_id) if booking else None
        return f"{label}-{customer.display_name}" if customer else f"{label}（已删除）"
    if source_type == "event":
        event = db.get(TemporaryEvent, source_id)
        return f"{label}-{event.name}" if event else f"{label}（已删除）"
    return label


def receivable_business_name(db: Session, receivable_id: str) -> str:
    item = db.get(Receivable, receivable_id)
    if item is None:
        return "应收记录（已删除）"
    return source_business_name(db, item.source_type, item.source_id)


def audit_action_label(action_type: str) -> str:
    return ACTION_LABELS.get(action_type, "其他业务操作")


def audit_entity_label(entity_type: str) -> str:
    return ENTITY_LABELS.get(entity_type, "业务记录")


def audit_entity_name(db: Session, entity_type: str, entity_id: str) -> str:
    if entity_type == "receivable":
        return receivable_business_name(db, entity_id)
    if entity_type in SOURCE_LABELS:
        return source_business_name(db, entity_type, entity_id)
    if entity_type == "event":
        return source_business_name(db, "event", entity_id)
    if entity_type == "private_package":
        return source_business_name(db, "private_package", entity_id)
    if entity_type == "private_lesson":
        return source_business_name(db, "private_lesson", entity_id)
    if entity_type == "venue_booking":
        return source_business_name(db, "venue_booking", entity_id)
    if entity_type == "schedule_entry":
        schedule = db.get(ScheduleEntry, entity_id)
        return schedule.title if schedule else "排期记录（已删除）"
    if entity_type == "fixed_class":
        fixed_class = db.get(FixedClass, entity_id)
        return fixed_class.name if fixed_class else "固定班（已删除）"
    if entity_type == "class_session":
        session = db.get(ClassSession, entity_id)
        fixed_class = db.get(FixedClass, session.fixed_class_id) if session else None
        return (
            f"{fixed_class.name}-第 {session.sequence_number} 节"
            if session and fixed_class
            else "固定班课次（已删除）"
        )
    if entity_type == "coach_fee":
        fee = db.get(CoachFee, entity_id)
        coach = db.get(CoachProfile, fee.coach_id) if fee else None
        return f"{coach.name if coach else '未知教练'}的教练费用"
    if entity_type == "payroll_settlement":
        settlement = db.get(PayrollSettlement, entity_id)
        coach = db.get(CoachProfile, settlement.coach_id) if settlement else None
        return f"{coach.name if coach else '未知教练'}的月度结算"
    if entity_type == "schedule_source":
        return "排期业务（已删除）"
    if entity_type == "court":
        court = db.get(Court, entity_id)
        return court.name if court else "场地（已删除）"
    if entity_type == "coach":
        coach = db.get(CoachProfile, entity_id)
        return coach.name if coach else "教练（已删除）"
    if entity_type == "venue":
        venue = db.get(Venue, entity_id)
        return venue.name if venue else "场馆设置"
    if entity_type == "venue_price_rules":
        return "场馆默认价格"
    if entity_type == "expense":
        expense = db.get(Expense, entity_id)
        return f"经营支出-{expense.payee}" if expense else "经营支出（已删除）"
    if entity_type == "other_income":
        income = db.get(OtherIncome, entity_id)
        return f"其他收入-{income.payer}" if income else "其他收入（已删除）"
    return audit_entity_label(entity_type)


def _audit_value(field: str, value: object) -> str:
    if value is None or value == "":
        return "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return f"{len(value)} 项"
    if isinstance(value, dict):
        return f"{len(value)} 项"
    if isinstance(value, str) and value in AUDIT_VALUE_LABELS:
        return AUDIT_VALUE_LABELS[value]
    if field.endswith("amount") or field in {
        "amount",
        "fixed_class_fee",
        "private_lesson_fee",
        "suggested_receivable",
        "actual_receivable",
    }:
        try:
            return f"¥{float(str(value)):.2f}"
        except ValueError:
            pass
    return str(value)


def audit_change_items(
    before: object, after: object
) -> list[dict[str, str]]:
    before_values = before if isinstance(before, dict) else {}
    after_values = after if isinstance(after, dict) else {}
    changes: list[dict[str, str]] = []
    for field in sorted(set(before_values) | set(after_values)):
        if field in AUDIT_HIDDEN_FIELDS or field.endswith("_id") or field.endswith("_ids"):
            continue
        old = before_values.get(field)
        new = after_values.get(field)
        if old == new:
            continue
        changes.append(
            {
                "field": AUDIT_FIELD_LABELS.get(field, field.replace("_", " ")),
                "before": _audit_value(field, old),
                "after": _audit_value(field, new),
            }
        )
    return changes


def audit_business_summary(before: object, after: object) -> str:
    changes = audit_change_items(before, after)
    if not changes:
        return "已记录该业务操作"
    return "；".join(
        f"{item['field']}：{item['before']} → {item['after']}" for item in changes[:3]
    )
