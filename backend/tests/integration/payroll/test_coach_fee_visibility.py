from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from shuttlecube.application.commands.coach_fees import ensure_coach_fee
from shuttlecube.application.queries.payroll import list_coach_fees
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.customers.models import Student
from shuttlecube.domain.identity.coach import CoachProfile
from shuttlecube.domain.private_lessons.models import PrivateLesson
from shuttlecube.domain.scheduling.court import Venue


def test_fee_api_returns_readable_source_and_audits_pending_adjustment(
    db: Session, authenticated
) -> None:
    client, csrf = authenticated
    coach = CoachProfile(name="陈教练")
    student = Student(name="胡东东")
    db.add_all([coach, student])
    db.flush()
    lesson = PrivateLesson(
        student_id=student.id,
        coach_id=coach.id,
        billing_mode="single",
        starts_at=datetime(2026, 8, 4, 10, tzinfo=UTC),
        ends_at=datetime(2026, 8, 4, 11, tzinfo=UTC),
        actual_receivable=Decimal("300.00"),
        coach_fee=Decimal("180.00"),
        status="completed",
    )
    db.add(lesson)
    db.flush()
    fee = ensure_coach_fee(
        db,
        source_type="private_lesson",
        source_id=lesson.id,
        coach_id=coach.id,
        occurred_at=lesson.ends_at,
        amount=lesson.coach_fee,
    )
    db.commit()

    response = client.get(
        f"/api/v1/coach-fees?coach_id={coach.id}&from=2026-08-01&to=2026-08-31"
    )
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["coach_name"] == "陈教练"
    assert item["business_name"] == "私教-胡东东"
    assert item["business_path"] == f"/private-lessons?lesson_id={lesson.id}"

    adjusted = client.patch(
        f"/api/v1/coach-fees/{fee.id}",
        headers=csrf,
        json={"adjustment_amount": -20, "reason": "临时代课调整", "version": fee.version},
    )
    assert adjusted.status_code == 200
    assert adjusted.json()["amount"] == 160
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action_type == "coach_fee.adjusted", AuditLog.entity_id == fee.id
        )
    )
    assert audit is not None
    assert audit.reason == "临时代课调整"


def test_fee_month_filter_uses_venue_timezone(db: Session) -> None:
    db.add(Venue(name="测试场馆", timezone="Asia/Shanghai"))
    ensure_coach_fee(
        db,
        source_type="private_lesson",
        source_id="month-boundary-lesson",
        coach_id="coach-boundary",
        occurred_at=datetime(2026, 8, 31, 17, tzinfo=UTC),
        amount=Decimal("100.00"),
    )
    db.commit()

    august = list_coach_fees(
        db,
        coach_id="coach-boundary",
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
    )
    september = list_coach_fees(
        db,
        coach_id="coach-boundary",
        period_start=date(2026, 9, 1),
        period_end=date(2026, 9, 30),
    )

    assert august.items == []
    assert len(september.items) == 1
