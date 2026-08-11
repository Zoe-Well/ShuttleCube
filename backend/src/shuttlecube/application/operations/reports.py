from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.report_capacity import build_court_capacity
from shuttlecube.application.queries.operations_report import _bounds, get_operations_report
from shuttlecube.application.queries.receivables import money, receivable_summary
from shuttlecube.domain.classes.class_models import ClassSession
from shuttlecube.domain.classes.enrollment_models import (
    AttendanceRecord,
    Enrollment,
    LessonUnitLedger,
)
from shuttlecube.domain.events.models import TemporaryEvent
from shuttlecube.domain.finance.models import Receivable
from shuttlecube.domain.operations.schemas import ReportMetric
from shuttlecube.domain.payroll.models import CoachFee, PayrollSettlement
from shuttlecube.domain.private_lessons.models import PrivateLesson
from shuttlecube.domain.venue_bookings.models import VenueBooking

METRIC_VERSION = 2


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _metric(
    key: str,
    value: Decimal | int,
    *,
    unit: str,
    calculated_at: datetime,
    scope: str = "period",
    precision: int = 2,
    data_status: str = "complete",
    source_refs: list[dict[str, object]] | None = None,
) -> ReportMetric:
    return ReportMetric.model_validate(
        {
            "metric_ref": f"metric:{key}",
            "metric_key": key,
            "scope": scope,
            "unit": unit,
            "value": value,
            "display_precision": precision,
            "calculated_at": calculated_at,
            "source_refs": source_refs or [],
            "data_status": data_status,
        }
    )


def _source_ref(
    kind: str,
    *,
    scope: RequestScope,
    starts_at: datetime | None,
    ends_at: datetime,
) -> dict[str, object]:
    window = (
        f"{starts_at.isoformat()}:{ends_at.isoformat()}"
        if starts_at is not None
        else f"as_of:{ends_at.isoformat()}"
    )
    return {"kind": kind, "id": f"{scope.venue_id}:{window}"}


def _status_counts(
    db: Session,
    *,
    model: Any,
    time_column: Any,
    scope: RequestScope,
    starts_at: datetime,
    effective_end: datetime,
) -> dict[str, int]:
    return {
        str(status): int(count)
        for status, count in db.execute(
            select(model.status, func.count(model.id))
            .where(
                model.organization_id == scope.organization_id,
                model.venue_id == scope.venue_id,
                time_column >= starts_at,
                time_column < effective_end,
            )
            .group_by(model.status)
        ).all()
    }


def _current_outstanding(
    db: Session,
    *,
    scope: RequestScope,
) -> tuple[Decimal, int]:
    receivables = db.scalars(
        select(Receivable).where(
            Receivable.organization_id == scope.organization_id,
            Receivable.venue_id == scope.venue_id,
            Receivable.status != "void",
        )
    ).all()
    total = Decimal("0")
    count = 0
    for item in receivables:
        outstanding = receivable_summary(db, item).outstanding_amount
        total += outstanding
        if outstanding > 0:
            count += 1
    return money(total), count


def build_report_facts(
    db: Session,
    *,
    scope: RequestScope,
    period_start: date,
    period_end: date,
    effective_end: datetime,
    calculated_at: datetime | None = None,
) -> dict[str, object]:
    calculated = calculated_at or datetime.now(UTC)
    legacy = get_operations_report(
        db,
        scope,
        period_start,
        period_end,
        effective_end=effective_end,
    )
    capacity = build_court_capacity(
        db,
        scope=scope,
        period_start=period_start,
        period_end=period_end,
        effective_end=effective_end,
    )
    starts_at, _, _ = _bounds(db, scope, period_start, period_end)
    session_counts = _status_counts(
        db,
        model=ClassSession,
        time_column=ClassSession.scheduled_start,
        scope=scope,
        starts_at=starts_at,
        effective_end=effective_end,
    )
    private_lesson_counts = _status_counts(
        db,
        model=PrivateLesson,
        time_column=PrivateLesson.starts_at,
        scope=scope,
        starts_at=starts_at,
        effective_end=effective_end,
    )
    venue_booking_counts = _status_counts(
        db,
        model=VenueBooking,
        time_column=VenueBooking.starts_at,
        scope=scope,
        starts_at=starts_at,
        effective_end=effective_end,
    )
    event_counts = _status_counts(
        db,
        model=TemporaryEvent,
        time_column=TemporaryEvent.starts_at,
        scope=scope,
        starts_at=starts_at,
        effective_end=effective_end,
    )
    enrollment_count = int(
        db.scalar(
            select(func.count(Enrollment.id)).where(
                Enrollment.organization_id == scope.organization_id,
                Enrollment.venue_id == scope.venue_id,
                Enrollment.created_at >= starts_at,
                Enrollment.created_at < effective_end,
            )
        )
        or 0
    )
    attendance_counts = {
        str(status): int(count)
        for status, count in db.execute(
            select(AttendanceRecord.status, func.count(AttendanceRecord.id))
            .join(ClassSession, ClassSession.id == AttendanceRecord.class_session_id)
            .where(
                AttendanceRecord.organization_id == scope.organization_id,
                AttendanceRecord.venue_id == scope.venue_id,
                ClassSession.organization_id == scope.organization_id,
                ClassSession.venue_id == scope.venue_id,
                ClassSession.scheduled_start >= starts_at,
                ClassSession.scheduled_start < effective_end,
                ClassSession.status == "completed",
            )
            .group_by(AttendanceRecord.status)
        ).all()
    }
    overdue_attendance = int(
        db.scalar(
            select(func.count(ClassSession.id)).where(
                ClassSession.organization_id == scope.organization_id,
                ClassSession.venue_id == scope.venue_id,
                ClassSession.status == "scheduled",
                ClassSession.scheduled_end < effective_end,
                ClassSession.attendance_finalized_at.is_(None),
            )
        )
        or 0
    )
    finalized_attendance_sessions = int(
        db.scalar(
            select(func.count(ClassSession.id)).where(
                ClassSession.organization_id == scope.organization_id,
                ClassSession.venue_id == scope.venue_id,
                ClassSession.scheduled_start >= starts_at,
                ClassSession.scheduled_start < effective_end,
                ClassSession.status == "completed",
                ClassSession.attendance_finalized_at.is_not(None),
            )
        )
        or 0
    )
    consumed_units_by_owner = {
        str(owner_type): abs(int(total or 0))
        for owner_type, total in db.execute(
            select(
                LessonUnitLedger.owner_type,
                func.coalesce(func.sum(LessonUnitLedger.delta), 0),
            )
            .where(
                LessonUnitLedger.organization_id == scope.organization_id,
                LessonUnitLedger.venue_id == scope.venue_id,
                LessonUnitLedger.operated_at >= starts_at,
                LessonUnitLedger.operated_at < effective_end,
                LessonUnitLedger.status == "effective",
                LessonUnitLedger.delta < 0,
            )
            .group_by(LessonUnitLedger.owner_type)
        ).all()
    }
    consumed_units = sum(consumed_units_by_owner.values())
    coach_fee_counts = _status_counts(
        db,
        model=CoachFee,
        time_column=CoachFee.occurred_at,
        scope=scope,
        starts_at=starts_at,
        effective_end=effective_end,
    )
    settlement_count = int(
        db.scalar(
            select(func.count(PayrollSettlement.id)).where(
                PayrollSettlement.organization_id == scope.organization_id,
                PayrollSettlement.venue_id == scope.venue_id,
                PayrollSettlement.status == "confirmed",
                PayrollSettlement.paid_at >= starts_at,
                PayrollSettlement.paid_at < effective_end,
            )
        )
        or 0
    )
    current_coach_pending_count = int(
        db.scalar(
            select(func.count(CoachFee.id)).where(
                CoachFee.organization_id == scope.organization_id,
                CoachFee.venue_id == scope.venue_id,
                CoachFee.status == "pending",
            )
        )
        or 0
    )
    outstanding_amount, outstanding_count = _current_outstanding(db, scope=scope)
    totals = capacity["totals"]
    assert isinstance(totals, dict)
    period_sources = {
        kind: [_source_ref(kind, scope=scope, starts_at=starts_at, ends_at=effective_end)]
        for kind in (
            "payment",
            "refund",
            "expense",
            "coach_fee",
            "payroll_settlement",
            "enrollment",
            "class_session",
            "private_lesson",
            "venue_booking",
            "event",
            "attendance_record",
            "lesson_unit_ledger",
            "schedule_allocation",
        )
    }
    as_of_sources = {
        kind: [_source_ref(kind, scope=scope, starts_at=None, ends_at=calculated)]
        for kind in ("receivable", "coach_fee")
    }
    completed_or_cancelled = {
        "class_session": session_counts.get("completed", 0)
        + session_counts.get("cancelled", 0),
        "private_lesson": private_lesson_counts.get("completed", 0)
        + private_lesson_counts.get("cancelled", 0),
        "venue_booking": venue_booking_counts.get("completed", 0)
        + venue_booking_counts.get("cancelled", 0),
        "event": event_counts.get("completed", 0) + event_counts.get("cancelled", 0),
    }
    business_closed_count = sum(completed_or_cancelled.values())
    business_cancelled_count = sum(
        counts.get("cancelled", 0)
        for counts in (
            session_counts,
            private_lesson_counts,
            venue_booking_counts,
            event_counts,
        )
    )
    business_cancellation_rate = (
        Decimal(business_cancelled_count) / Decimal(business_closed_count)
        if business_closed_count
        else Decimal("0")
    )
    class_closed_count = completed_or_cancelled["class_session"]
    class_cancellation_rate = (
        Decimal(session_counts.get("cancelled", 0)) / Decimal(class_closed_count)
        if class_closed_count
        else Decimal("0")
    )
    available_hours = Decimal(str(totals["available_hours"]))
    capacity_status = (
        "insufficient"
        if available_hours <= 0
        else "data_quality_issue"
        if capacity["data_quality"]
        else "complete"
    )
    metrics = [
        _metric("cash_income", legacy["income"], unit="cny", calculated_at=calculated, source_refs=period_sources["payment"]),
        _metric("cash_refunds", legacy["refunds"], unit="cny", calculated_at=calculated, source_refs=period_sources["refund"]),
        _metric("operating_expense", legacy["expense"], unit="cny", calculated_at=calculated, source_refs=period_sources["expense"]),
        _metric("cash_profit", legacy["profit"], unit="cny", calculated_at=calculated, source_refs=[*period_sources["payment"], *period_sources["refund"], *period_sources["expense"]]),
        _metric(
            "outstanding_as_of",
            outstanding_amount,
            unit="cny",
            scope="as_of",
            calculated_at=calculated,
            source_refs=as_of_sources["receivable"],
        ),
        _metric("outstanding_receivables_as_of", outstanding_count, unit="count", scope="as_of", calculated_at=calculated, precision=0, source_refs=as_of_sources["receivable"]),
        _metric("coach_fee_earned", legacy["coach_earned"], unit="cny", calculated_at=calculated, source_refs=period_sources["coach_fee"]),
        _metric("coach_fee_pending", legacy["coach_pending"], unit="cny", calculated_at=calculated, source_refs=period_sources["coach_fee"]),
        _metric("coach_fee_settled", legacy["coach_settled"], unit="cny", calculated_at=calculated, source_refs=period_sources["payroll_settlement"]),
        _metric("coach_fee_current_pending_as_of", legacy["current_coach_pending"], unit="cny", scope="as_of", calculated_at=calculated, source_refs=as_of_sources["coach_fee"]),
        _metric("coach_fee_current_pending_count_as_of", current_coach_pending_count, unit="count", scope="as_of", calculated_at=calculated, precision=0, source_refs=as_of_sources["coach_fee"]),
        _metric("coach_fee_items_earned", sum(count for status, count in coach_fee_counts.items() if status != "void"), unit="count", calculated_at=calculated, precision=0, source_refs=period_sources["coach_fee"]),
        _metric("coach_fee_items_pending", coach_fee_counts.get("pending", 0), unit="count", calculated_at=calculated, precision=0, source_refs=period_sources["coach_fee"]),
        _metric("payroll_settlements", settlement_count, unit="count", calculated_at=calculated, precision=0, source_refs=period_sources["payroll_settlement"]),
        _metric("enrollments_created", enrollment_count, unit="count", calculated_at=calculated, precision=0, source_refs=period_sources["enrollment"]),
        _metric("attendance_records", sum(attendance_counts.values()), unit="count", calculated_at=calculated, precision=0, source_refs=period_sources["attendance_record"]),
        _metric("attendance_finalized_sessions", finalized_attendance_sessions, unit="count", calculated_at=calculated, precision=0, source_refs=period_sources["class_session"]),
        _metric("attendance_overdue_sessions", overdue_attendance, unit="count", calculated_at=calculated, precision=0, source_refs=period_sources["class_session"]),
        _metric("lesson_units_consumed", consumed_units, unit="lesson_unit", calculated_at=calculated, precision=0, source_refs=period_sources["lesson_unit_ledger"]),
        _metric("fixed_class_lesson_units_consumed", consumed_units_by_owner.get("enrollment", 0), unit="lesson_unit", calculated_at=calculated, precision=0, source_refs=period_sources["lesson_unit_ledger"]),
        _metric("private_lesson_units_consumed", consumed_units_by_owner.get("private_package", 0), unit="lesson_unit", calculated_at=calculated, precision=0, source_refs=period_sources["lesson_unit_ledger"]),
        _metric("business_cancellation_rate", business_cancellation_rate, unit="ratio", calculated_at=calculated, precision=4, data_status="complete" if business_closed_count else "insufficient", source_refs=[*period_sources["class_session"], *period_sources["private_lesson"], *period_sources["venue_booking"], *period_sources["event"]]),
        _metric("class_session_cancellation_rate", class_cancellation_rate, unit="ratio", calculated_at=calculated, precision=4, data_status="complete" if class_closed_count else "insufficient", source_refs=period_sources["class_session"]),
        _metric("court_base_business_hours", Decimal(str(totals["base_business_hours"])), unit="hour", calculated_at=calculated, source_refs=period_sources["schedule_allocation"]),
        _metric("court_block_unavailable_hours", Decimal(str(totals["court_block_unavailable_hours"])), unit="hour", calculated_at=calculated, source_refs=period_sources["schedule_allocation"]),
        _metric("court_available_hours", available_hours, unit="hour", calculated_at=calculated, source_refs=period_sources["schedule_allocation"]),
        _metric("court_commercial_usage_hours", Decimal(str(totals["commercial_usage_hours"])), unit="hour", calculated_at=calculated, source_refs=period_sources["schedule_allocation"]),
        _metric("court_outside_business_hours", Decimal(str(totals["outside_business_hours"])), unit="hour", calculated_at=calculated, source_refs=period_sources["schedule_allocation"]),
        _metric(
            "court_raw_utilization",
            Decimal(str(totals["raw_utilization"])),
            unit="ratio",
            calculated_at=calculated,
            precision=4,
            data_status=capacity_status,
            source_refs=period_sources["schedule_allocation"],
        ),
        _metric(
            "court_display_utilization",
            Decimal(str(totals["display_utilization"])),
            unit="ratio",
            calculated_at=calculated,
            precision=2,
            data_status=capacity_status,
            source_refs=period_sources["schedule_allocation"],
        ),
    ]
    for prefix, counts, source_kind, statuses in (
        ("class_sessions", session_counts, "class_session", ("scheduled", "completed", "cancelled")),
        ("private_lessons", private_lesson_counts, "private_lesson", ("booked", "completed", "cancelled")),
        ("venue_bookings", venue_booking_counts, "venue_booking", ("booked", "confirmed", "completed", "cancelled")),
        ("temporary_events", event_counts, "event", ("confirmed", "completed", "cancelled")),
    ):
        metrics.extend(
            _metric(
                f"{prefix}_{status}",
                counts.get(status, 0),
                unit="count",
                calculated_at=calculated,
                precision=0,
                source_refs=period_sources[source_kind],
            )
            for status in statuses
        )
    metrics.extend(
        _metric(
            f"attendance_{status}",
            attendance_counts.get(status, 0),
            unit="count",
            calculated_at=calculated,
            precision=0,
            source_refs=period_sources["attendance_record"],
        )
        for status in ("present", "leave", "absent", "unprocessed")
    )
    caveats: list[dict[str, object]] = []
    if available_hours <= 0:
        caveats.append(
            {
                "code": "court_capacity_insufficient",
                "message": "当前期间没有可计算的场地可营业容量，利用率不参与异常判断。",
            }
        )
    for issue in capacity["data_quality"]:
        caveats.append({"code": issue, "message": "场地排期存在需要人工复核的数据质量提示。"})
    return {
        "metric_version": METRIC_VERSION,
        "metrics": [metric.model_dump(mode="json") for metric in metrics],
        "breakdowns": {
            "income_by_source": {
                str(key): str(value) for key, value in dict(legacy["income_by_source"]).items()
            },
            "fixed_class_finance": _json_safe(legacy["fixed_class_finance"]),
            "court_capacity": capacity,
            "session_counts": session_counts,
            "private_lesson_counts": private_lesson_counts,
            "venue_booking_counts": venue_booking_counts,
            "event_counts": event_counts,
            "attendance_counts": attendance_counts,
            "lesson_units_by_owner": consumed_units_by_owner,
            "coach_fee_counts": coach_fee_counts,
        },
        "source_refs": [
            *[refs[0] for refs in period_sources.values()],
            *[refs[0] for refs in as_of_sources.values()],
        ],
        "caveats": caveats,
    }
