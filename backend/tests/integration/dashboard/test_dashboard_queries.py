from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.application.commands.classes import enroll_student
from shuttlecube.application.commands.coach_fees import ensure_coach_fee
from shuttlecube.application.commands.expenses import create_expense
from shuttlecube.application.commands.payments import record_payment
from shuttlecube.application.commands.payroll import create_payroll_settlement
from shuttlecube.application.commands.refunds import record_refund
from shuttlecube.application.queries.dashboard import get_dashboard, get_pending_attendance
from shuttlecube.application.queries.operations_report import get_operations_report
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.finance.models import Receivable
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.domain.scheduling.models import ScheduleAllocation, ScheduleEntry


def test_dashboard_and_report_use_cash_facts_without_double_counting_refunds(
    db: Session, admin
) -> None:
    now = datetime(2026, 8, 4, 10, tzinfo=UTC)
    receivable = Receivable(
        source_type="venue_booking",
        source_id="booking-1",
        suggested_amount=Decimal("100"),
        actual_amount=Decimal("100"),
    )
    db.add_all(
        [
            receivable,
            ScheduleEntry(
                source_type="venue_booking",
                source_id="booking-1",
                title="散客订场",
                starts_at=now,
                ends_at=datetime(2026, 8, 4, 11, tzinfo=UTC),
            ),
        ]
    )
    db.commit()
    payment = record_payment(
        db,
        receivable,
        paid_at=now,
        amount=Decimal("100"),
        method="cash",
        payer_name=None,
        received_by=None,
        notes=None,
        actor_id=admin.id,
        idempotency_key="report-payment",
        request_id="report-payment-request",
    )
    record_refund(
        db,
        receivable,
        payment_id=payment.id,
        refunded_at=now,
        suggested_amount=Decimal("20"),
        actual_amount=Decimal("20"),
        reason="部分取消",
        lesson_units_to_remove=0,
        actor_id=admin.id,
        idempotency_key="report-refund",
        request_id="report-refund-request",
    )
    create_expense(
        db,
        category="equipment",
        spent_at=now,
        amount=Decimal("30"),
        payee="器材商",
        payment_method="cash",
        source_type=None,
        source_id=None,
        notes=None,
        actor_id=admin.id,
        idempotency_key="report-expense",
        request_id="report-expense-request",
    )
    ensure_coach_fee(
        db,
        source_type="private_lesson",
        source_id="lesson-report",
        coach_id="coach-report",
        occurred_at=now,
        amount=Decimal("50"),
    )
    db.commit()

    report = get_operations_report(db, date(2026, 8, 1), date(2026, 8, 31))
    assert report["income"] == Decimal("100.00")
    assert report["refunds"] == Decimal("20.00")
    assert report["expense"] == Decimal("30.00")
    assert report["profit"] == Decimal("50.00")
    assert report["coach_pending"] == Decimal("50.00")
    assert report["coach_earned"] == Decimal("50.00")
    assert report["current_coach_pending"] == Decimal("50.00")

    dashboard = get_dashboard(db, date(2026, 8, 4))
    assert dashboard["today_counts"]["venue_booking"] == 1
    assert dashboard["month_finance"]["profit"] == Decimal("50.00")


def test_report_uses_actual_payroll_payment_for_settled_coach_amount(db: Session, admin) -> None:
    coach = CoachProfile(name="结算教练", phone="13800000001")
    db.add(coach)
    db.flush()
    occurred_at = datetime(2026, 8, 4, 10, tzinfo=UTC)
    ensure_coach_fee(
        db,
        source_type="private_lesson",
        source_id="lesson-settlement-report",
        coach_id=coach.id,
        occurred_at=occurred_at,
        amount=Decimal("100.00"),
    )
    create_payroll_settlement(
        db,
        coach_id=coach.id,
        period_month=date(2026, 8, 1),
        actual_amount=Decimal("120.00"),
        adjustment_reason="增加交通补贴",
        paid_at=occurred_at,
        actor_id=admin.id,
        idempotency_key="report-payroll-settlement",
        request_id="report-payroll-settlement-request",
    )

    report = get_operations_report(db, date(2026, 8, 1), date(2026, 8, 31))
    assert report["coach_pending"] == Decimal("0.00")
    assert report["coach_earned"] == Decimal("100.00")
    assert report["current_coach_pending"] == Decimal("0.00")
    assert report["coach_settled"] == Decimal("120.00")


def test_dashboard_counts_coaches_with_pending_fees_instead_of_fee_records(
    db: Session,
) -> None:
    pending_coach = CoachProfile(name="待结教练", phone="13800000002")
    settled_coach = CoachProfile(name="已结教练", phone="13800000003")
    db.add_all([pending_coach, settled_coach])
    db.flush()
    occurred_at = datetime(2026, 8, 4, 10, tzinfo=UTC)
    ensure_coach_fee(
        db,
        source_type="private_lesson",
        source_id="pending-lesson-1",
        coach_id=pending_coach.id,
        occurred_at=occurred_at,
        amount=Decimal("100.00"),
    )
    ensure_coach_fee(
        db,
        source_type="private_lesson",
        source_id="pending-lesson-2",
        coach_id=pending_coach.id,
        occurred_at=occurred_at,
        amount=Decimal("200.00"),
    )
    settled_fee = ensure_coach_fee(
        db,
        source_type="private_lesson",
        source_id="settled-lesson",
        coach_id=settled_coach.id,
        occurred_at=occurred_at,
        amount=Decimal("300.00"),
    )
    settled_fee.status = "settled"
    db.commit()

    dashboard = get_dashboard(db, date(2026, 8, 4))

    assert dashboard["pending_counts"]["coach_fees"] == 1


def test_report_groups_fixed_class_cash_by_class_name(db: Session, admin) -> None:
    student = Student(name="周同学")
    fixed_class = FixedClass(
        name="周末提高班",
        class_type="training",
        start_date=date(2026, 8, 1),
        default_start_time=time(18),
        duration_minutes=60,
        session_count=10,
        capacity=12,
        default_coach_id="coach-class-report",
        required_court_count=1,
        student_unit_price=Decimal("100.00"),
        status="active",
    )
    db.add_all([student, fixed_class])
    db.commit()
    enrollment = enroll_student(
        db,
        student_id=student.id,
        fixed_class=fixed_class,
        enrolled_on=date(2026, 8, 4),
        purchased_units=4,
        actual_receivable=Decimal("400.00"),
        reason=None,
        actor_id=admin.id,
    )
    receivable = db.scalar(
        select(Receivable).where(
            Receivable.source_type == "enrollment", Receivable.source_id == enrollment.id
        )
    )
    assert receivable is not None
    payment = record_payment(
        db,
        receivable,
        paid_at=datetime(2026, 8, 4, 10, tzinfo=UTC),
        amount=Decimal("300.00"),
        method="wechat",
        payer_name=None,
        received_by=None,
        notes=None,
        actor_id=admin.id,
        idempotency_key="class-report-payment",
        request_id="class-report-payment-request",
    )
    record_refund(
        db,
        receivable,
        payment_id=payment.id,
        refunded_at=datetime(2026, 8, 4, 11, tzinfo=UTC),
        suggested_amount=Decimal("50.00"),
        actual_amount=Decimal("50.00"),
        reason="减少报名课时",
        lesson_units_to_remove=0,
        actor_id=admin.id,
        idempotency_key="class-report-refund",
        request_id="class-report-refund-request",
    )

    report = get_operations_report(db, date(2026, 8, 1), date(2026, 8, 31))
    assert report["income_by_source"] == {"enrollment": Decimal("300.00")}
    assert report["income_by_class"] == {fixed_class.id: Decimal("300.00")}
    assert report["fixed_class_finance"] == [
        {
            "class_id": fixed_class.id,
            "class_name": "周末提高班",
            "payment_amount": Decimal("300.00"),
            "refund_amount": Decimal("50.00"),
            "net_received": Decimal("250.00"),
            "outstanding_amount": Decimal("100.00"),
        }
    ]

    # SQLite drops timezone information from DateTime columns. The dashboard
    # must still aggregate fixed-class finance and ending-class reminders.
    db.add(
        ClassSession(
            fixed_class_id=fixed_class.id,
            sequence_number=1,
            scheduled_start=datetime(2026, 8, 10, 10, tzinfo=UTC),
            scheduled_end=datetime(2026, 8, 10, 11, tzinfo=UTC),
            actual_coach_id=fixed_class.default_coach_id,
        )
    )
    db.commit()
    dashboard = get_dashboard(db, date(2026, 8, 4))
    assert dashboard["month_finance"]["income"] == Decimal("300.00")
    assert dashboard["month_finance"]["outstanding"] == Decimal("100.00")
    assert dashboard["pending_counts"]["ending_classes"] == 1


def test_report_returns_court_names_for_utilization(db: Session) -> None:
    venue = Venue(name="测试场馆")
    db.add(venue)
    db.flush()
    court = Court(venue_id=venue.id, code="C01", name="1 号场地")
    entry = ScheduleEntry(
        source_type="court_block",
        source_id="block-1",
        title="场地占用",
        starts_at=datetime(2026, 8, 4, 10, tzinfo=UTC),
        ends_at=datetime(2026, 8, 4, 11, tzinfo=UTC),
    )
    db.add_all([court, entry])
    db.flush()
    db.add(
        ScheduleAllocation(
            schedule_entry_id=entry.id,
            resource_type="court",
            resource_id=court.id,
            starts_at=entry.starts_at,
            ends_at=entry.ends_at,
        )
    )
    db.add(
        ScheduleAllocation(
            schedule_entry_id=entry.id,
            resource_type="court",
            resource_id="legacy-court-text",
            starts_at=entry.starts_at,
            ends_at=entry.ends_at,
        )
    )
    db.commit()

    report = get_operations_report(db, date(2026, 8, 4), date(2026, 8, 4))

    assert report["court_names"] == {court.id: "1 号场地"}
    assert court.id in report["court_utilization"]
    assert "legacy-court-text" not in report["court_utilization"]


def test_ending_classes_only_use_future_sessions_and_respect_selected_range(
    db: Session,
) -> None:
    classes = [
        FixedClass(
            name=name,
            class_type="training",
            start_date=date(2026, 7, 1),
            default_start_time=time(18),
            duration_minutes=60,
            session_count=10,
            capacity=12,
            default_coach_id=f"coach-{index}",
            required_court_count=1,
            student_unit_price=Decimal("100.00"),
            status="active",
        )
        for index, name in enumerate(
            ["仅有过去课程", "七天内结束", "十五天内结束", "三十天内结束", "三十天后结束"]
        )
    ]
    db.add_all(classes)
    db.flush()
    session_ends = [
        datetime(2026, 8, 2, 11, tzinfo=UTC),
        datetime(2026, 8, 10, 11, tzinfo=UTC),
        datetime(2026, 8, 18, 11, tzinfo=UTC),
        datetime(2026, 8, 28, 11, tzinfo=UTC),
        datetime(2026, 9, 10, 11, tzinfo=UTC),
    ]
    db.add_all(
        [
            ClassSession(
                fixed_class_id=fixed_class.id,
                sequence_number=1,
                scheduled_start=session_end - timedelta(hours=1),
                scheduled_end=session_end,
                actual_coach_id=fixed_class.default_coach_id,
            )
            for fixed_class, session_end in zip(classes, session_ends, strict=True)
        ]
    )
    db.commit()

    assert get_dashboard(db, date(2026, 8, 4), 7)["pending_counts"]["ending_classes"] == 1
    assert get_dashboard(db, date(2026, 8, 4), 15)["pending_counts"]["ending_classes"] == 2
    assert get_dashboard(db, date(2026, 8, 4), 30)["pending_counts"]["ending_classes"] == 3


def test_attention_apis_return_matching_ending_class_list(
    db: Session, authenticated
) -> None:
    client, _ = authenticated
    fixed_class = FixedClass(
        name="周三进阶班",
        class_type="training",
        start_date=date(2026, 8, 1),
        default_start_time=time(18),
        duration_minutes=60,
        session_count=2,
        capacity=12,
        default_coach_id="coach-makeup",
        required_court_count=1,
        student_unit_price=Decimal("100.00"),
        status="active",
    )
    db.add(fixed_class)
    db.flush()
    origin_session = ClassSession(
        fixed_class_id=fixed_class.id,
        sequence_number=1,
        scheduled_start=datetime(2026, 8, 3, 10, tzinfo=UTC),
        scheduled_end=datetime(2026, 8, 3, 11, tzinfo=UTC),
        actual_coach_id=fixed_class.default_coach_id,
        status="completed",
    )
    future_session = ClassSession(
        fixed_class_id=fixed_class.id,
        sequence_number=2,
        scheduled_start=datetime(2026, 8, 10, 10, tzinfo=UTC),
        scheduled_end=datetime(2026, 8, 10, 11, tzinfo=UTC),
        actual_coach_id=fixed_class.default_coach_id,
    )
    db.add_all([origin_session, future_session])
    db.flush()
    db.commit()

    classes_response = client.get(
        "/api/v1/classes?business_date=2026-08-04&ending_within_days=7"
    )
    dashboard_response = client.get(
        "/api/v1/dashboard?business_date=2026-08-04&ending_within_days=7"
    )
    assert classes_response.status_code == 200, classes_response.json()
    assert dashboard_response.status_code == 200, dashboard_response.json()
    assert (
        len(classes_response.json())
        == dashboard_response.json()["pending_counts"]["ending_classes"]
        == 1
    )
    assert classes_response.json()[0]["name"] == "周三进阶班"
    assert classes_response.json()[0]["remaining_scheduled_sessions"] == 1


def test_today_pending_attendance_returns_sessions_with_class_context(
    db: Session, authenticated
) -> None:
    client, _ = authenticated
    coach = CoachProfile(name="陈教练", phone="13800000000")
    db.add(coach)
    db.flush()
    fixed_class = FixedClass(
        name="周二基础班",
        class_type="training",
        start_date=date(2026, 8, 4),
        default_start_time=time(18),
        duration_minutes=60,
        session_count=1,
        capacity=8,
        default_coach_id=coach.id,
        required_court_count=1,
        student_unit_price=Decimal("100.00"),
        status="active",
    )
    db.add(fixed_class)
    db.flush()
    session = ClassSession(
        fixed_class_id=fixed_class.id,
        sequence_number=1,
        scheduled_start=datetime(2026, 8, 4, 10, tzinfo=UTC),
        scheduled_end=datetime(2026, 8, 4, 11, tzinfo=UTC),
        actual_coach_id=coach.id,
    )
    db.add(session)
    db.commit()

    pending = get_pending_attendance(db, date(2026, 8, 4))
    assert len(pending) == 1
    assert pending[0].fixed_class.name == "周二基础班"
    assert pending[0].coach_name == "陈教练"

    response = client.get(
        "/api/v1/dashboard/pending-attendance?business_date=2026-08-04"
    )
    assert response.status_code == 200, response.json()
    assert response.json() == [
        {
            "session_id": session.id,
            "class_id": fixed_class.id,
            "class_name": "周二基础班",
            "sequence_number": 1,
            "scheduled_start": "2026-08-04T10:00:00Z",
            "scheduled_end": "2026-08-04T11:00:00Z",
            "coach_name": "陈教练",
            "active_enrollment_count": 0,
        }
    ]
