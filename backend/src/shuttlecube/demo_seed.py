from __future__ import annotations

import argparse
import hashlib
import json
import random
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.access import capabilities_for_role
from shuttlecube.application.operations.cases import upsert_detected_case
from shuttlecube.application.operations.detectors import DetectorRegistry
from shuttlecube.application.operations.policies import activate_policy, create_policy_draft
from shuttlecube.domain.classes.class_models import ClassSession, FixedClass
from shuttlecube.domain.classes.enrollment_models import (
    AttendanceRecord,
    Enrollment,
    LessonUnitLedger,
    MakeupRecord,
)
from shuttlecube.domain.customers.models import (
    Guardian,
    Student,
    StudentGuardian,
    WalkInCustomer,
)
from shuttlecube.domain.events.models import EventParticipant, TemporaryEvent
from shuttlecube.domain.finance.models import Expense, OtherIncome, Payment, Receivable, Refund
from shuttlecube.domain.identity.coach import CoachProfile, CoachRate
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.identity.organization_models import (
    Organization,
    OrganizationMembership,
    VenueMembership,
)
from shuttlecube.domain.operations.models import CaseActivity, OperationCase
from shuttlecube.domain.operations.schemas import OperationsPolicyConfig
from shuttlecube.domain.payroll.models import CoachFee, PayrollSettlement
from shuttlecube.domain.private_lessons.models import PrivateLesson, PrivateLessonPackage
from shuttlecube.domain.scheduling.court import Court, Venue
from shuttlecube.domain.scheduling.models import CourtBlock, ScheduleAllocation, ScheduleEntry
from shuttlecube.domain.venue_bookings.models import VenueBooking, VenuePriceRule
from shuttlecube.infrastructure.security.passwords import hash_password

SEED = 20260812
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "Demo@123456"
BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")


def money(value: int | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def scoped(organization: Organization, venue: Venue) -> dict[str, str]:
    return {"organization_id": organization.id, "venue_id": venue.id}


class DemoSeeder:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.random = random.Random(SEED)
        self.now = datetime.now(UTC).replace(second=0, microsecond=0)
        self.today = self.now.astimezone(BEIJING_TIMEZONE).date()
        self.organization = Organization(name="星跃羽毛球俱乐部")
        self.admin = SystemUser(
            username=ADMIN_USERNAME,
            display_name="林店长",
            password_hash=hash_password(ADMIN_PASSWORD),
            is_active=True,
        )
        self.venue = Venue(
            organization_id=self.organization.id,
            name="星跃羽毛球馆（滨江店）",
            timezone="Asia/Shanghai",
            weekday_open_time=time(9, 0),
            weekday_close_time=time(23, 0),
            weekend_open_time=time(8, 0),
            weekend_close_time=time(23, 0),
            active_for_operations=True,
            write_tools_enabled=False,
            model_enabled=True,
            model_enabled_by=self.admin.id,
            model_enabled_at=self.now - timedelta(days=5),
        )
        self.courts: list[Court] = []
        self.coaches: list[CoachProfile] = []
        self.students: list[Student] = []
        self.guardians: list[Guardian] = []
        self.walk_ins: list[WalkInCustomer] = []
        self.enrollment_balances: dict[str, int] = {}
        self.package_balances: dict[str, int] = {}

    def at(self, days: int, hour: int, minute: int = 0) -> datetime:
        target_date = self.today + timedelta(days=days)
        return datetime.combine(target_date, time(hour, minute), BEIJING_TIMEZONE).astimezone(UTC)

    def previous_weekday_at(self, weekday: int, hour: int, minute: int = 0) -> datetime:
        days_back = (self.today.weekday() - weekday) % 7 or 7
        return self.at(-days_back, hour, minute)

    def add(self, *items: object) -> None:
        self.db.add_all(items)

    def create_schedule(
        self,
        *,
        source_type: str,
        source_id: str,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        court_ids: list[str],
        coach_id: str | None = None,
        status: str = "confirmed",
        notes: str | None = None,
    ) -> ScheduleEntry:
        entry = ScheduleEntry(
            **scoped(self.organization, self.venue),
            source_type=source_type,
            source_id=source_id,
            title=title,
            starts_at=starts_at,
            ends_at=ends_at,
            status=status,
            notes=notes,
        )
        self.db.add(entry)
        self.db.flush()
        for court_id in court_ids:
            self.db.add(
                ScheduleAllocation(
                    **scoped(self.organization, self.venue),
                    schedule_entry_id=entry.id,
                    resource_type="court",
                    resource_id=court_id,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    active=status != "cancelled",
                )
            )
        if coach_id:
            self.db.add(
                ScheduleAllocation(
                    **scoped(self.organization, self.venue),
                    schedule_entry_id=entry.id,
                    resource_type="coach",
                    resource_id=coach_id,
                    starts_at=starts_at,
                    ends_at=ends_at,
                    active=status != "cancelled",
                )
            )
        return entry

    def seed_identity_and_resources(self) -> None:
        self.add(self.organization, self.admin)
        self.db.flush()
        self.db.add(self.venue)
        self.db.flush()
        organization_membership = OrganizationMembership(
            organization_id=self.organization.id,
            user_id=self.admin.id,
            status="active",
            organization_role="owner",
            reviewed_by=self.admin.id,
            reviewed_at=self.now - timedelta(days=180),
        )
        venue_membership = VenueMembership(
            organization_membership_id=organization_membership.id,
            organization_id=self.organization.id,
            venue_id=self.venue.id,
            role_key="owner",
            status="active",
        )
        self.add(organization_membership, venue_membership)
        self.db.flush()

        court_names = [
            "1号标准场", "2号标准场", "3号标准场", "4号标准场",
            "5号训练场", "6号训练场", "7号比赛场", "8号比赛场",
        ]
        for index, name in enumerate(court_names, start=1):
            court = Court(
                venue_id=self.venue.id,
                code=str(index),
                name=name,
                is_active=index != 6,
                notes="灯光检修，暂不开放" if index == 6 else None,
            )
            self.courts.append(court)
            self.db.add(court)

        coach_specs = [
            ("周启航", "13800001001", "成人进阶、双打战术"),
            ("陈雨桐", "13800001002", "少儿启蒙、步法训练"),
            ("赵子昂", "13800001003", "私教、体能强化"),
            ("孙婉宁", "13800001004", "女子训练、青少年竞赛"),
            ("何俊杰", "13800001005", "企业团建、成人零基础"),
            ("王教练（停用）", "13800001006", "历史教练资料"),
        ]
        for index, (name, phone, specialties) in enumerate(coach_specs):
            coach = CoachProfile(
                organization_id=self.organization.id,
                name=name,
                phone=phone,
                specialties=specialties,
                is_active=index != 5,
            )
            self.coaches.append(coach)
            self.db.add(coach)
            self.db.flush()
            for business_type, amount in (
                ("fixed_class", 180 + index * 20),
                ("private_lesson", 150 + index * 25),
                ("event", 300 + index * 30),
            ):
                self.db.add(
                    CoachRate(
                        organization_id=self.organization.id,
                        coach_id=coach.id,
                        business_type=business_type,
                        amount=money(amount),
                        effective_from=self.today - timedelta(days=240),
                    )
                )

        price_rules = [
            ("工作日白天", "weekday", time(9), time(18), 55, 10),
            ("工作日晚间", "weekday", time(18), time(23), 85, 20),
            ("周末全天", "weekend", time(8), time(23), 100, 30),
        ]
        for name, day_type, start, end, price, priority in price_rules:
            self.db.add(
                VenuePriceRule(
                    **scoped(self.organization, self.venue),
                    name=name,
                    day_type=day_type,
                    time_start=start,
                    time_end=end,
                    price_per_court_hour=money(price),
                    priority=priority,
                    is_active=True,
                )
            )

    def seed_customers(self) -> None:
        surnames = ["陈", "林", "王", "李", "张", "周", "吴", "徐", "孙", "赵"]
        given_names = ["一诺", "子涵", "梓轩", "雨桐", "浩然", "可欣", "俊熙", "思妍", "嘉豪", "安琪"]
        levels = ["少儿启蒙", "少儿基础", "青少年进阶", "成人零基础", "成人中级"]
        for index in range(42):
            surname = surnames[index % len(surnames)]
            name = surname + given_names[(index * 3) % len(given_names)]
            student = Student(
                organization_id=self.organization.id,
                name=name,
                gender="男" if index % 2 == 0 else "女",
                birth_date=date(2012 + index % 8, 1 + index % 12, 1 + index % 26),
                phone=f"1391000{index:04d}" if index >= 30 else None,
                level_tags=levels[index % len(levels)],
                is_active=index != 41,
                notes="膝盖旧伤，训练前注意热身" if index == 34 else None,
            )
            guardian = Guardian(
                organization_id=self.organization.id,
                name=f"{surname}{'女士' if index % 2 else '先生'}",
                phone=f"1372000{index:04d}",
                wechat_note=f"家长-{name}",
                notes="优先微信联系" if index % 4 == 0 else None,
            )
            self.students.append(student)
            self.guardians.append(guardian)
            self.add(student, guardian)
            self.db.add(
                StudentGuardian(
                    organization_id=self.organization.id,
                    student_id=student.id,
                    guardian_id=guardian.id,
                    relationship_label="母亲" if index % 2 else "父亲",
                    is_primary_contact=True,
                )
            )
        for index in range(14):
            customer = WalkInCustomer(
                organization_id=self.organization.id,
                display_name=f"散客{chr(65 + index)}",
                phone=f"1363000{index:04d}" if index != 13 else None,
                wechat_note=f"订场客户{index + 1}" if index % 3 == 0 else None,
                notes="公司长期订场联系人" if index == 0 else None,
            )
            self.walk_ins.append(customer)
            self.db.add(customer)

    def add_receivable(
        self,
        *,
        source_type: str,
        source_id: str,
        amount: Decimal,
        created_days_ago: int,
        paid: Decimal = Decimal("0"),
        status: str | None = None,
        payer: str | None = None,
    ) -> Receivable:
        receivable = Receivable(
            **scoped(self.organization, self.venue),
            source_type=source_type,
            source_id=source_id,
            suggested_amount=amount,
            actual_amount=amount,
            status=status or ("settled" if paid >= amount else "partial" if paid > 0 else "open"),
            created_at=self.now - timedelta(days=created_days_ago),
            updated_at=self.now - timedelta(days=max(created_days_ago - 1, 0)),
        )
        self.db.add(receivable)
        self.db.flush()
        if paid > 0:
            self.db.add(
                Payment(
                    **scoped(self.organization, self.venue),
                    receivable_id=receivable.id,
                    paid_at=self.now - timedelta(days=max(created_days_ago - 2, 0)),
                    amount=paid,
                    method=["wechat", "alipay", "bank_transfer", "cash"][created_days_ago % 4],
                    payer_name=payer,
                    received_by="前台",
                    operated_by=self.admin.id,
                    notes="演示数据：正常收款",
                    idempotency_key=f"demo-payment-{receivable.id}",
                )
            )
        return receivable

    def add_ledger(
        self,
        *,
        owner_type: str,
        owner_id: str,
        delta: int,
        source_type: str,
        source_id: str,
        reason: str,
        happened_at: datetime,
    ) -> LessonUnitLedger:
        balances = self.enrollment_balances if owner_type == "enrollment" else self.package_balances
        before = balances.get(owner_id, 0)
        after = before + delta
        balances[owner_id] = after
        ledger = LessonUnitLedger(
            **scoped(self.organization, self.venue),
            owner_type=owner_type,
            owner_id=owner_id,
            change_type="purchase" if delta > 0 else "consume",
            delta=delta,
            balance_before=before,
            balance_after=after,
            source_type=source_type,
            source_id=source_id,
            reason=reason,
            operated_by=self.admin.id,
            operated_at=happened_at,
            idempotency_key=f"demo-ledger-{owner_type}-{owner_id}-{source_type}-{source_id}",
        )
        self.db.add(ledger)
        self.db.flush()
        return ledger

    def seed_fixed_classes(self) -> None:
        definitions = [
            ("周一成人中级班", "成人班", "成人中级", 0, 19, 30, 90, 12, 10, 135, 240),
            ("周二少儿启蒙班", "少儿班", "7-10岁", 1, 18, 30, 75, 16, 10, 120, 220),
            ("周三青少年进阶班", "青少年班", "青少年进阶", 2, 19, 0, 90, 12, 7, 150, 260),
            ("周五成人零基础班", "成人班", "成人零基础", 4, 20, 0, 90, 10, 0, 130, 220),
            ("周日少儿基础班", "少儿班", "9-12岁", 6, 9, 30, 90, 14, 9, 125, 230),
        ]
        student_cursor = 0
        for class_index, (
            name, class_type, level, weekday, hour, minute, duration, capacity,
            enrollment_count, unit_price, coach_fee,
        ) in enumerate(definitions):
            start_date = self.today - timedelta(days=70)
            fixed_class = FixedClass(
                **scoped(self.organization, self.venue),
                name=name,
                class_type=class_type,
                age_or_level=level,
                recurrence_rule=f"FREQ=WEEKLY;BYDAY={['MO','TU','WE','TH','FR','SA','SU'][weekday]}",
                start_date=start_date,
                default_start_time=time(hour, minute),
                duration_minutes=duration,
                session_count=12,
                capacity=capacity,
                default_coach_id=self.coaches[class_index % 5].id,
                required_court_count=1,
                student_unit_price=money(unit_price),
                coach_fee_per_session=money(coach_fee),
                status="active",
                notes="演示班级：包含历史课程、未来排期和多种考勤状态",
            )
            self.db.add(fixed_class)
            self.db.flush()
            enrollments: list[Enrollment] = []
            for enrollment_index in range(enrollment_count):
                student = self.students[(student_cursor + enrollment_index) % 38]
                purchased = 12
                enrollment = Enrollment(
                    **scoped(self.organization, self.venue),
                    student_id=student.id,
                    fixed_class_id=fixed_class.id,
                    enrolled_on=self.today - timedelta(days=65 - enrollment_index),
                    purchased_units=purchased,
                    unit_price=money(unit_price),
                    suggested_receivable=money(unit_price * purchased),
                    actual_receivable=money(unit_price * purchased),
                    is_midterm=enrollment_index == enrollment_count - 1 and class_index == 2,
                    price_adjustment_reason="插班按剩余课次计费" if enrollment_index == enrollment_count - 1 and class_index == 2 else None,
                    status="active",
                    notes="老学员续班" if enrollment_index % 5 == 0 else None,
                )
                enrollments.append(enrollment)
                self.db.add(enrollment)
                self.add_ledger(
                    owner_type="enrollment",
                    owner_id=enrollment.id,
                    delta=purchased,
                    source_type="enrollment",
                    source_id=enrollment.id,
                    reason="购买固定班课时",
                    happened_at=self.now - timedelta(days=65 - enrollment_index),
                )
                total = money(unit_price * purchased)
                if class_index == 0 and enrollment_index == 0:
                    paid = money(0)
                    age = 42
                elif class_index == 1 and enrollment_index == 1:
                    paid = total / 2
                    age = 18
                else:
                    paid = total
                    age = 62 - enrollment_index
                self.add_receivable(
                    source_type="enrollment",
                    source_id=enrollment.id,
                    amount=total,
                    created_days_ago=age,
                    paid=paid,
                    payer=self.guardians[(student_cursor + enrollment_index) % 38].name,
                )
            student_cursor += enrollment_count

            # The zero-enrollment Friday class deliberately has no sessions. This demonstrates
            # the production rule that empty classes do not create unusable attendance plans.
            if not enrollments:
                continue
            for sequence in range(1, 13):
                day_offset = -63 + (sequence - 1) * 7 + ((weekday - self.today.weekday()) % 7)
                starts = self.at(day_offset, hour, minute)
                ends = starts + timedelta(minutes=duration)
                status = "scheduled"
                finalized_at: datetime | None = None
                replacement_decision: str | None = None
                cancellation_reason: str | None = None
                if sequence <= 7:
                    status = "completed"
                    finalized_at = ends + timedelta(minutes=20)
                if class_index == 0 and sequence == 8:
                    # Past scheduled session with no finalized attendance -> overdue case.
                    starts = self.previous_weekday_at(weekday, hour, minute)
                    ends = starts + timedelta(minutes=duration)
                    status = "scheduled"
                if class_index == 2 and sequence == 9:
                    starts = self.previous_weekday_at(weekday, hour, minute)
                    ends = starts + timedelta(minutes=duration)
                    status = "cancelled"
                    replacement_decision = "pending"
                    cancellation_reason = "教练临时发烧，等待与学员确认补课时间"
                entry = self.create_schedule(
                    source_type="class_session",
                    source_id="pending",
                    title=f"{name} · 第{sequence}节",
                    starts_at=starts,
                    ends_at=ends,
                    court_ids=[self.courts[class_index % 5].id],
                    coach_id=fixed_class.default_coach_id,
                    status="cancelled" if status == "cancelled" else "confirmed",
                )
                session = ClassSession(
                    **scoped(self.organization, self.venue),
                    fixed_class_id=fixed_class.id,
                    sequence_number=sequence,
                    scheduled_start=starts,
                    scheduled_end=ends,
                    actual_coach_id=fixed_class.default_coach_id,
                    status=status,
                    replacement_decision=replacement_decision,
                    cancellation_reason=cancellation_reason,
                    attendance_finalized_at=finalized_at,
                    schedule_entry_id=entry.id,
                )
                entry.source_id = session.id
                self.db.add(session)
                self.db.flush()
                if status == "completed":
                    self.db.add(
                        CoachFee(
                            **scoped(self.organization, self.venue),
                            coach_id=fixed_class.default_coach_id,
                            source_type="class_session",
                            source_id=session.id,
                            occurred_at=ends,
                            base_amount=money(coach_fee),
                            adjustment_amount=money(20 if sequence == 3 and class_index == 1 else 0),
                            adjustment_reason="临时代课补贴" if sequence == 3 and class_index == 1 else None,
                            status="pending",
                        )
                    )
                    for attendee_index, enrollment in enumerate(enrollments):
                        attendance_status = ["present", "present", "present", "leave", "absent"][
                            (attendee_index + sequence) % 5
                        ]
                        deduct = 0 if attendance_status == "leave" else 1
                        ledger = None
                        if deduct:
                            ledger = self.add_ledger(
                                owner_type="enrollment",
                                owner_id=enrollment.id,
                                delta=-1,
                                source_type="class_session",
                                source_id=session.id,
                                reason=f"{name}第{sequence}节考勤扣课",
                                happened_at=ends,
                            )
                        attendance = AttendanceRecord(
                            **scoped(self.organization, self.venue),
                            class_session_id=session.id,
                            student_id=enrollment.student_id,
                            enrollment_id=enrollment.id,
                            status=attendance_status,
                            deduct_units=deduct,
                            grants_makeup=attendance_status == "leave" and sequence % 2 == 0,
                            lesson_ledger_id=ledger.id if ledger else None,
                            decision_note="提前请假，保留补课资格" if attendance_status == "leave" else None,
                        )
                        self.db.add(attendance)
                        if attendance.grants_makeup:
                            self.db.flush()
                            self.db.add(
                                MakeupRecord(
                                    **scoped(self.organization, self.venue),
                                    student_id=enrollment.student_id,
                                    origin_attendance_id=attendance.id,
                                    status="pending",
                                    created_by=self.admin.id,
                                    notes="等待安排同级别班级补课",
                                )
                            )

        self.db.add(
            FixedClass(
                **scoped(self.organization, self.venue),
                name="企业团体定制班（草稿）",
                class_type="企业班",
                age_or_level="成人混合水平",
                recurrence_rule="FREQ=WEEKLY;BYDAY=TH",
                start_date=self.today + timedelta(days=20),
                default_start_time=time(19),
                duration_minutes=120,
                session_count=8,
                capacity=16,
                default_coach_id=self.coaches[4].id,
                required_court_count=2,
                student_unit_price=money(180),
                coach_fee_per_session=money(450),
                status="draft",
                notes="等待企业确认人员名单和开班日期",
            )
        )

    def seed_private_lessons(self) -> None:
        for index in range(10):
            student = self.students[30 + index]
            coach = self.coaches[index % 4]
            purchased = [10, 12, 20][index % 3]
            package = PrivateLessonPackage(
                **scoped(self.organization, self.venue),
                student_id=student.id,
                bound_coach_id=coach.id,
                purchased_units=purchased,
                unit_price=money(260 + (index % 3) * 40),
                actual_receivable=money(purchased * (260 + (index % 3) * 40)),
                valid_until=self.now + timedelta(days=12 if index == 0 else 20 if index == 1 else 120),
                status="active" if index != 9 else "expired",
                notes="希望周末上午上课" if index % 3 == 0 else None,
            )
            self.db.add(package)
            self.add_ledger(
                owner_type="private_package",
                owner_id=package.id,
                delta=purchased,
                source_type="private_package",
                source_id=package.id,
                reason="购买私教课包",
                happened_at=self.now - timedelta(days=50 - index),
            )
            total = package.actual_receivable
            paid = total if index not in {1, 8} else (total / 2 if index == 1 else money(0))
            self.add_receivable(
                source_type="private_package",
                source_id=package.id,
                amount=total,
                created_days_ago=48 - index,
                paid=paid,
                payer=student.name,
            )
            completed_count = purchased - (2 if index == 0 else 3 if index == 1 else 6)
            completed_count = max(1, min(completed_count, 6))
            for lesson_index in range(completed_count):
                starts = self.at(-35 + lesson_index * 5 + index % 2, 10 + index % 5)
                ends = starts + timedelta(minutes=60)
                entry = self.create_schedule(
                    source_type="private_lesson",
                    source_id="pending",
                    title=f"{student.name} · 私教课",
                    starts_at=starts,
                    ends_at=ends,
                    court_ids=[self.courts[(index + lesson_index) % 5].id],
                    coach_id=coach.id,
                )
                lesson = PrivateLesson(
                    **scoped(self.organization, self.venue),
                    student_id=student.id,
                    coach_id=coach.id,
                    package_id=package.id,
                    billing_mode="package",
                    starts_at=starts,
                    ends_at=ends,
                    actual_receivable=money(0),
                    coach_fee=money(160 + index % 3 * 20),
                    status="completed",
                    schedule_entry_id=entry.id,
                )
                entry.source_id = lesson.id
                self.db.add(lesson)
                self.add_ledger(
                    owner_type="private_package",
                    owner_id=package.id,
                    delta=-1,
                    source_type="private_lesson",
                    source_id=lesson.id,
                    reason="完成私教课扣减课时",
                    happened_at=ends,
                )
                self.db.add(
                    CoachFee(
                        **scoped(self.organization, self.venue),
                        coach_id=coach.id,
                        source_type="private_lesson",
                        source_id=lesson.id,
                        occurred_at=ends,
                        base_amount=lesson.coach_fee,
                        adjustment_amount=money(0),
                        status="pending",
                    )
                )
            if index < 5:
                starts = self.at(2 + index, 14 + index)
                ends = starts + timedelta(minutes=60)
                entry = self.create_schedule(
                    source_type="private_lesson",
                    source_id="pending",
                    title=f"{student.name} · 已预约私教",
                    starts_at=starts,
                    ends_at=ends,
                    court_ids=[self.courts[(index + 2) % 5].id],
                    coach_id=coach.id,
                )
                lesson = PrivateLesson(
                    **scoped(self.organization, self.venue),
                    student_id=student.id,
                    coach_id=coach.id,
                    package_id=package.id,
                    billing_mode="package",
                    starts_at=starts,
                    ends_at=ends,
                    actual_receivable=money(0),
                    coach_fee=money(180),
                    status="booked",
                    schedule_entry_id=entry.id,
                )
                entry.source_id = lesson.id
                self.db.add(lesson)

        student = self.students[40]
        starts = self.at(-6, 20)
        ends = starts + timedelta(minutes=90)
        entry = self.create_schedule(
            source_type="private_lesson",
            source_id="pending",
            title=f"{student.name} · 单次私教",
            starts_at=starts,
            ends_at=ends,
            court_ids=[self.courts[4].id],
            coach_id=self.coaches[2].id,
        )
        lesson = PrivateLesson(
            **scoped(self.organization, self.venue),
            student_id=student.id,
            coach_id=self.coaches[2].id,
            package_id=None,
            billing_mode="single",
            starts_at=starts,
            ends_at=ends,
            actual_receivable=money(420),
            coach_fee=money(220),
            status="completed",
            schedule_entry_id=entry.id,
            notes="临时体验课",
        )
        entry.source_id = lesson.id
        self.db.add(lesson)
        self.add_receivable(
            source_type="private_lesson",
            source_id=lesson.id,
            amount=money(420),
            created_days_ago=7,
            paid=money(420),
            payer=student.name,
        )
        self.db.add(
            CoachFee(
                **scoped(self.organization, self.venue),
                coach_id=lesson.coach_id,
                source_type="private_lesson",
                source_id=lesson.id,
                occurred_at=ends,
                base_amount=lesson.coach_fee,
                adjustment_amount=money(0),
                status="pending",
            )
        )

    def seed_bookings_events_and_blocks(self) -> None:
        rules = list(self.db.scalars(select(VenuePriceRule)).all())
        for index in range(18):
            days = -28 + index * 2
            starts = self.at(days, 18 + index % 4)
            ends = starts + timedelta(hours=2)
            status = "completed" if days < 0 else "confirmed"
            if index == 4:
                status = "cancelled"
            court_ids = [self.courts[index % 5].id]
            suggested = money(170 if starts.weekday() < 5 else 200)
            actual = suggested if index % 5 else suggested - money(20)
            booking = VenueBooking(
                **scoped(self.organization, self.venue),
                customer_id=self.walk_ins[index % len(self.walk_ins)].id,
                starts_at=starts,
                ends_at=ends,
                court_ids_csv=",".join(court_ids),
                price_rule_id=rules[1 if starts.weekday() < 5 else 2].id,
                suggested_receivable=suggested,
                actual_receivable=actual,
                price_adjustment_reason="长期客户优惠" if index % 5 == 0 else None,
                payment_status="unpaid" if index in {15, 16} else "paid",
                status=status,
                notes="固定双打球友群" if index % 4 == 0 else None,
            )
            entry = self.create_schedule(
                source_type="venue_booking",
                source_id=booking.id,
                title=f"{self.walk_ins[index % len(self.walk_ins)].display_name} · 订场",
                starts_at=starts,
                ends_at=ends,
                court_ids=court_ids,
                status="cancelled" if status == "cancelled" else "confirmed",
            )
            booking.schedule_entry_id = entry.id
            self.db.add(booking)
            self.add_receivable(
                source_type="venue_booking",
                source_id=booking.id,
                amount=actual,
                created_days_ago=max(1, -days + 2),
                paid=actual if booking.payment_status == "paid" and status != "cancelled" else money(0),
                status="void" if status == "cancelled" else None,
                payer=self.walk_ins[index % len(self.walk_ins)].display_name,
            )

        event_specs = [
            ("青少年积分赛", "tournament", -18, 9, 6, 3200, 900, "completed"),
            ("星河科技企业团建", "corporate", -8, 14, 4, 4800, 600, "completed"),
            ("周末新生体验营", "open_day", 6, 9, 3, 1800, 350, "confirmed"),
            ("暑期双打交流赛", "tournament", 16, 9, 6, 3600, 1000, "confirmed"),
            ("雨天社区友谊赛", "community", -3, 13, 2, 800, 200, "cancelled"),
        ]
        for index, (name, event_type, days, hour, duration, income, expense, status) in enumerate(event_specs):
            starts = self.at(days, hour)
            ends = starts + timedelta(hours=duration)
            court_ids = [court.id for court in self.courts[: min(4, 2 + index % 3)]]
            event_item = TemporaryEvent(
                **scoped(self.organization, self.venue),
                event_type=event_type,
                name=name,
                starts_at=starts,
                ends_at=ends,
                court_ids_csv=",".join(court_ids),
                coach_id=self.coaches[index % 5].id,
                coach_fee=money(500 + index * 80),
                suggested_receivable=money(income),
                actual_receivable=money(income),
                expense_amount=money(expense),
                track_participants=True,
                requires_attendance=True,
                status=status,
                notes="含饮用水、比赛用球和简单奖品",
            )
            entry = self.create_schedule(
                source_type="event",
                source_id=event_item.id,
                title=name,
                starts_at=starts,
                ends_at=ends,
                court_ids=court_ids,
                coach_id=event_item.coach_id,
                status="cancelled" if status == "cancelled" else "confirmed",
            )
            event_item.schedule_entry_id = entry.id
            self.db.add(event_item)
            self.db.flush()
            for participant_index in range(8 + index * 2):
                self.db.add(
                    EventParticipant(
                        **scoped(self.organization, self.venue),
                        event_id=event_item.id,
                        student_id=self.students[(participant_index + index * 5) % 40].id,
                        attendance_status=(
                            "present" if status == "completed" and participant_index % 6 else
                            "absent" if status == "completed" else None
                        ),
                    )
                )
            receivable = self.add_receivable(
                source_type="event",
                source_id=event_item.id,
                amount=money(income),
                created_days_ago=max(2, -days + 10),
                paid=money(income if status == "completed" else income // 2 if status == "confirmed" else 0),
                status="void" if status == "cancelled" else None,
                payer=name,
            )
            if index == 0:
                payment = self.db.scalar(select(Payment).where(Payment.receivable_id == receivable.id))
                if payment:
                    self.db.add(
                        Refund(
                            **scoped(self.organization, self.venue),
                            receivable_id=receivable.id,
                            payment_id=payment.id,
                            refunded_at=self.now - timedelta(days=12),
                            suggested_amount=money(200),
                            actual_amount=money(200),
                            reason="一名参赛学员赛前因伤退出",
                            operated_by=self.admin.id,
                            idempotency_key=f"demo-refund-{receivable.id}",
                        )
                    )
            if status == "completed":
                self.db.add(
                    CoachFee(
                        **scoped(self.organization, self.venue),
                        coach_id=event_item.coach_id,
                        source_type="event",
                        source_id=event_item.id,
                        occurred_at=ends,
                        base_amount=event_item.coach_fee,
                        adjustment_amount=money(0),
                        status="pending",
                    )
                )

        block = CourtBlock(
            **scoped(self.organization, self.venue),
            reason="7号场地地胶保养",
            starts_at=self.at(3, 9),
            ends_at=self.at(3, 17),
            status="confirmed",
            notes="施工期间不对外售卖",
        )
        self.db.add(block)
        self.create_schedule(
            source_type="court_block",
            source_id=block.id,
            title=block.reason,
            starts_at=block.starts_at,
            ends_at=block.ends_at,
            court_ids=[self.courts[6].id],
        )

    def seed_finance_and_payroll(self) -> None:
        expense_specs = [
            ("rent", "滨江体育中心", 38500, -30, "bank_transfer", "八月场地租金"),
            ("utilities", "城市电力", 4860, -12, "bank_transfer", "七月电费"),
            ("shuttlecocks", "飞羽体育用品", 3280, -20, "wechat", "比赛用球及训练用球"),
            ("equipment", "劲速体育", 1680, -16, "alipay", "球网、握把胶和标志桶"),
            ("marketing", "本地生活推广", 2200, -10, "wechat", "暑期招生推广"),
            ("cleaning", "洁净物业", 1800, -5, "bank_transfer", "月度保洁服务"),
            ("maintenance", "安盾消防", 760, -3, "cash", "灭火器年检"),
        ]
        for index, (category, payee, amount, days, method, notes) in enumerate(expense_specs):
            self.db.add(
                Expense(
                    **scoped(self.organization, self.venue),
                    category=category,
                    spent_at=self.at(days, 11),
                    amount=money(amount),
                    payee=payee,
                    payment_method=method,
                    operated_by=self.admin.id,
                    notes=notes,
                    idempotency_key=f"demo-expense-{index}",
                )
            )
        for index, (category, payer, amount, days) in enumerate(
            [
                ("vending", "自动售货机分成", 860, -25),
                ("sponsorship", "飞羽体育赞助", 3000, -15),
                ("stringing", "球拍穿线服务", 1260, -4),
            ]
        ):
            self.db.add(
                OtherIncome(
                    **scoped(self.organization, self.venue),
                    category=category,
                    received_at=self.at(days, 16),
                    amount=money(amount),
                    payer=payer,
                    payment_method="wechat" if index != 1 else "bank_transfer",
                    operated_by=self.admin.id,
                    notes="演示数据",
                    idempotency_key=f"demo-other-income-{index}",
                )
            )

        self.db.flush()
        period_end = self.today.replace(day=1) - timedelta(days=1)
        period_start = period_end.replace(day=1)
        for coach in self.coaches[:3]:
            fees = list(
                self.db.scalars(
                    select(CoachFee).where(
                        CoachFee.coach_id == coach.id,
                        CoachFee.occurred_at >= datetime.combine(period_start, time.min, UTC),
                        CoachFee.occurred_at <= datetime.combine(period_end, time.max, UTC),
                        CoachFee.status == "pending",
                    )
                ).all()
            )
            if not fees:
                continue
            calculated = sum((fee.base_amount + fee.adjustment_amount for fee in fees), money(0))
            adjustment = money(100 if coach == self.coaches[0] else 0)
            expense = Expense(
                **scoped(self.organization, self.venue),
                category="coach_payroll",
                spent_at=self.at(-5, 10),
                amount=calculated + adjustment,
                payee=coach.name,
                payment_method="bank_transfer",
                source_type="payroll_settlement",
                source_id="pending",
                operated_by=self.admin.id,
                notes=f"{period_start:%Y-%m} 教练费结算",
                idempotency_key=f"demo-payroll-expense-{coach.id}",
            )
            settlement = PayrollSettlement(
                **scoped(self.organization, self.venue),
                coach_id=coach.id,
                period_start=period_start,
                period_end=period_end,
                calculated_amount=calculated,
                adjustment_amount=adjustment,
                actual_amount=calculated + adjustment,
                adjustment_reason="月度带班奖励" if adjustment else None,
                paid_at=self.at(-5, 10),
                settled_by=self.admin.id,
                status="confirmed",
                expense_id=expense.id,
                idempotency_key=f"demo-payroll-{coach.id}-{period_start}",
            )
            expense.source_id = settlement.id
            self.db.add(expense)
            self.db.flush()
            self.db.add(settlement)
            self.db.flush()
            for fee in fees:
                fee.status = "settled"
                fee.settlement_id = settlement.id

    def seed_operations(self) -> None:
        scope = RequestScope(
            organization_id=self.organization.id,
            venue_id=self.venue.id,
            user_id=self.admin.id,
            membership_id="demo-owner",
            capabilities=capabilities_for_role("owner"),
        )
        config = {
            "receivable_followup": {"aging_days": 7, "escalation_days": 30, "max_attempts": 4},
            "renewal": {
                "fixed_class_days": 30,
                "private_package_expiry_days": 30,
                "private_package_remaining_units": 3,
                "cadence_days": 7,
            },
            "attendance": {"grace_hours": 24},
            "replacement": {"window_days": 14, "slot_minutes": 30, "resource_mode": "original_only"},
            "reports": {
                "min_sample_size": 5,
                "income_decline": "0.20",
                "refund_ratio": "0.10",
                "expense_growth": "0.20",
                "outstanding": "1000.00",
                "cancellation_rate": "0.10",
                "low_utilization": "0.30",
                "coach_pending": "1000.00",
            },
            "runtime": {"case_sla_days": 3, "approval_expiry_minutes": 60, "retry_limit": 2},
        }
        validated = OperationsPolicyConfig.model_validate(config)
        policy = create_policy_draft(
            self.db,
            scope=scope,
            schema_version=1,
            config=validated.model_dump(mode="json"),
            name="日常运营规则",
        )
        activate_policy(self.db, scope=scope, policy_id=policy.id, expected_version=policy.version)
        self.db.flush()

        for definition in DetectorRegistry.default().enabled():
            assert definition.implementation is not None
            evidence_items = definition.implementation(self.db, scope, policy, self.now)
            for evidence in evidence_items[:30]:
                upsert_detected_case(
                    self.db,
                    scope=scope,
                    definition=definition,
                    evidence=evidence,
                    case_sla_days=validated.runtime.case_sla_days,
                    detected_at=self.now,
                )
        self.db.flush()
        followup_case = self.db.scalar(
            select(OperationCase)
            .where(OperationCase.case_type == "receivable_followup")
            .order_by(OperationCase.first_detected_at)
        )
        if followup_case:
            followup_case.assigned_to = self.admin.id
            followup_case.assigned_by = self.admin.id
            followup_case.assigned_at = self.now - timedelta(days=2)
            self.db.add(
                CaseActivity(
                    organization_id=self.organization.id,
                    venue_id=self.venue.id,
                    case_id=followup_case.id,
                    case_occurrence_no=followup_case.occurrence_no,
                    activity_type="contact_result",
                    channel="wechat",
                    outcome_code="promised_payment",
                    summary="家长已确认账单，承诺本周五前补齐余款。",
                    happened_at=self.now - timedelta(days=1),
                    next_check_at=self.now + timedelta(days=2),
                    operated_by=self.admin.id,
                    source="user",
                )
            )

    def run(self) -> dict[str, int | str]:
        self.seed_identity_and_resources()
        self.db.flush()
        self.seed_customers()
        self.db.flush()
        self.seed_fixed_classes()
        self.seed_private_lessons()
        self.db.flush()
        self.seed_bookings_events_and_blocks()
        self.db.flush()
        self.seed_finance_and_payroll()
        self.db.flush()
        self.seed_operations()
        self.db.commit()
        return self.summary()

    def summary(self) -> dict[str, int | str]:
        models = {
            "students": Student,
            "guardians": Guardian,
            "coaches": CoachProfile,
            "courts": Court,
            "fixed_classes": FixedClass,
            "class_sessions": ClassSession,
            "enrollments": Enrollment,
            "attendance_records": AttendanceRecord,
            "private_packages": PrivateLessonPackage,
            "private_lessons": PrivateLesson,
            "venue_bookings": VenueBooking,
            "events": TemporaryEvent,
            "receivables": Receivable,
            "payments": Payment,
            "refunds": Refund,
            "expenses": Expense,
            "coach_fees": CoachFee,
            "operation_cases": OperationCase,
        }
        result: dict[str, int | str] = {
            "venue": self.venue.name,
            "username": ADMIN_USERNAME,
        }
        for key, model in models.items():
            result[key] = int(self.db.scalar(select(func.count()).select_from(model)) or 0)
        return result


def _sqlite_engine(database: Path) -> Engine:
    engine = create_engine(f"sqlite+pysqlite:///{database.resolve().as_posix()}")

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection: object, _record: object) -> None:
        cursor = connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a migrated ShuttleCube SQLite database")
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    database = args.database.resolve()
    if not database.is_file():
        raise SystemExit(f"Database does not exist: {database}")
    with Session(_sqlite_engine(database)) as db:
        seeder = DemoSeeder(db)
        try:
            summary = seeder.run()
        except Exception:
            db.rollback()
            raise
    payload = {
        **summary,
        "password_sha256": hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
