from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import IntEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.api.serialization import as_utc
from shuttlecube.application.queries.operations_report import _bounds, get_operations_report
from shuttlecube.application.queries.receivables import receivable_summary
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import Enrollment
from shuttlecube.domain.finance.models import Receivable
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.payroll.models import CoachFee
from shuttlecube.domain.scheduling.models import ScheduleEntry


@dataclass(frozen=True)
class EndingClassSummary:
    fixed_class: FixedClass
    last_scheduled_end: datetime
    remaining_scheduled_sessions: int


class EndingWithinDays(IntEnum):
    DAYS_7 = 7
    DAYS_15 = 15
    DAYS_30 = 30


@dataclass(frozen=True)
class PendingAttendanceSummary:
    session: ClassSession
    fixed_class: FixedClass
    coach_name: str
    active_enrollment_count: int


def get_pending_attendance(
    db: Session, scope: RequestScope, business_date: date
) -> list[PendingAttendanceSummary]:
    starts_at, ends_at, _ = _bounds(db, scope, business_date, business_date)
    sessions = list(
        db.scalars(
            select(ClassSession)
            .join(FixedClass, FixedClass.id == ClassSession.fixed_class_id)
            .where(
                FixedClass.status == "active",
                FixedClass.organization_id == scope.organization_id,
                FixedClass.venue_id == scope.venue_id,
                ClassSession.organization_id == scope.organization_id,
                ClassSession.venue_id == scope.venue_id,
                ClassSession.status == "scheduled",
                ClassSession.scheduled_start < ends_at,
                ClassSession.scheduled_end > starts_at,
                ClassSession.attendance_finalized_at.is_(None),
            )
            .order_by(ClassSession.scheduled_start, ClassSession.sequence_number)
        ).all()
    )
    result: list[PendingAttendanceSummary] = []
    for session in sessions:
        fixed_class = db.get(FixedClass, session.fixed_class_id)
        if fixed_class is None:
            continue
        coach = db.get(CoachProfile, session.actual_coach_id)
        active_enrollment_count = len(
            list(
                db.scalars(
                    select(Enrollment.id).where(
                        Enrollment.fixed_class_id == fixed_class.id,
                        Enrollment.organization_id == scope.organization_id,
                        Enrollment.venue_id == scope.venue_id,
                        Enrollment.status == "active",
                    )
                ).all()
            )
        )
        result.append(
            PendingAttendanceSummary(
                session=session,
                fixed_class=fixed_class,
                coach_name=coach.name if coach else "未关联系统教练",
                active_enrollment_count=active_enrollment_count,
            )
        )
    return result


def get_ending_classes(
    db: Session, scope: RequestScope, business_date: date, ending_within_days: int
) -> list[EndingClassSummary]:
    starts_at, ends_at, _ = _bounds(db, scope, business_date, business_date)
    window_end = ends_at + timedelta(days=ending_within_days)
    summaries: list[EndingClassSummary] = []
    for fixed_class in db.scalars(
        select(FixedClass).where(
            FixedClass.organization_id == scope.organization_id,
            FixedClass.venue_id == scope.venue_id,
            FixedClass.status == "active",
        )
    ).all():
        future_sessions = list(
            db.scalars(
                select(ClassSession).where(
                    ClassSession.fixed_class_id == fixed_class.id,
                    ClassSession.organization_id == scope.organization_id,
                    ClassSession.venue_id == scope.venue_id,
                    ClassSession.status == "scheduled",
                    ClassSession.scheduled_end >= starts_at,
                )
            ).all()
        )
        if not future_sessions:
            continue
        last_scheduled_end = max(as_utc(row.scheduled_end) for row in future_sessions)
        if last_scheduled_end <= window_end:
            summaries.append(
                EndingClassSummary(
                    fixed_class=fixed_class,
                    last_scheduled_end=last_scheduled_end,
                    remaining_scheduled_sessions=len(future_sessions),
                )
            )
    return sorted(summaries, key=lambda item: (item.last_scheduled_end, item.fixed_class.name))


def get_dashboard(
    db: Session,
    scope: RequestScope,
    business_date: date,
    ending_within_days: int = 30,
) -> dict[str, object]:
    starts_at, ends_at, _ = _bounds(db, scope, business_date, business_date)
    schedule = list(
        db.scalars(
            select(ScheduleEntry).where(
                ScheduleEntry.status.notin_(["cancelled", "rescheduled"]),
                ScheduleEntry.organization_id == scope.organization_id,
                ScheduleEntry.venue_id == scope.venue_id,
                ScheduleEntry.starts_at < ends_at,
                ScheduleEntry.ends_at > starts_at,
            )
        ).all()
    )
    today_counts: dict[str, int] = {}
    for row in schedule:
        if row.source_type == "class_session":
            session = db.get(ClassSession, row.source_id)
            fixed_class = db.get(FixedClass, session.fixed_class_id) if session else None
            if fixed_class and fixed_class.status == "archived":
                continue
        today_counts[row.source_type] = today_counts.get(row.source_type, 0) + 1
    outstanding = [
        receivable_summary(db, row)
        for row in db.scalars(
            select(Receivable).where(
                Receivable.organization_id == scope.organization_id,
                Receivable.venue_id == scope.venue_id,
                Receivable.status != "void",
            )
        ).all()
    ]
    pending_attendance = len(get_pending_attendance(db, scope, business_date))
    pending_coaches = db.scalar(
        select(func.count(func.distinct(CoachFee.coach_id))).where(
            CoachFee.status == "pending"
            ,CoachFee.organization_id == scope.organization_id
            ,CoachFee.venue_id == scope.venue_id
        )
    ) or 0
    ending_classes = get_ending_classes(db, scope, business_date, ending_within_days)
    month_start = business_date.replace(day=1)
    finance = get_operations_report(db, scope, month_start, business_date)
    return {
        "business_date": business_date,
        "today_counts": today_counts,
        "pending_counts": {
            "attendance": pending_attendance,
            "receivables": sum(1 for item in outstanding if item.outstanding_amount > Decimal(0)),
            "ending_classes": len(ending_classes),
            "coach_fees": pending_coaches,
        },
        "ending_within_days": ending_within_days,
        "month_finance": {
            "income": finance["income"],
            "refunds": finance["refunds"],
            "expense": finance["expense"],
            "profit": finance["profit"],
            "outstanding": finance["outstanding"],
        },
    }
