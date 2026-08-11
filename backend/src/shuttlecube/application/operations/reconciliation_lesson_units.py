from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shuttlecube.api.dependencies import RequestScope
from shuttlecube.application.operations.reconciliation import (
    AffectedReference,
    InvariantCheck,
    ReconciliationImpact,
    ReconciliationRule,
    RepairEntryPoint,
    failed_result,
)
from shuttlecube.domain.classes.class_models import ClassSession
from shuttlecube.domain.classes.enrollment_models import AttendanceRecord, LessonUnitLedger
from shuttlecube.domain.finance.models import Receivable, Refund
from shuttlecube.domain.private_lessons.models import PrivateLesson


def check_ledger_chains(db: Session, scope: RequestScope):
    rows = db.scalars(
        select(LessonUnitLedger)
        .where(
            LessonUnitLedger.organization_id == scope.organization_id,
            LessonUnitLedger.venue_id == scope.venue_id,
        )
        .order_by(
            LessonUnitLedger.owner_type,
            LessonUnitLedger.owner_id,
            LessonUnitLedger.operated_at,
            LessonUnitLedger.id,
        )
    ).all()
    owners: dict[tuple[str, str], list[LessonUnitLedger]] = defaultdict(list)
    for row in rows:
        owners[(row.owner_type, row.owner_id)].append(row)
    failures = []
    for (owner_type, owner_id), owner_rows in owners.items():
        effective = [row for row in owner_rows if row.status == "effective"]
        formula_bad = [
            row.id for row in effective if row.balance_after != row.balance_before + row.delta
        ]
        negative = [row.id for row in effective if row.balance_after < 0 or row.balance_before < 0]
        chain_bad = [
            current.id
            for previous, current in zip(effective, effective[1:], strict=False)
            if previous.balance_after != current.balance_before
        ]
        keys = [row.idempotency_key for row in owner_rows]
        duplicate_keys = sorted({key for key in keys if keys.count(key) > 1})
        if not (formula_bad or negative or chain_bad or duplicate_keys):
            continue
        failures.append(
            failed_result(
                scope=scope,
                rule_key="ledger.chain",
                rule_version=1,
                subject_type=owner_type,
                subject_id=owner_id,
                severity="critical" if negative else "high",
                invariants=[
                    InvariantCheck(
                        key="balance_formula",
                        expected="balance_after = balance_before + delta",
                        actual=f"invalid ledger ids: {formula_bad}",
                        passed=not formula_bad,
                    ),
                    InvariantCheck(
                        key="balance_chain",
                        expected="adjacent effective ledger balances connect",
                        actual=f"broken at ledger ids: {chain_bad}",
                        passed=not chain_bad,
                    ),
                    InvariantCheck(
                        key="non_negative_balance",
                        expected="effective balances are non-negative",
                        actual=f"negative ledger ids: {negative}",
                        passed=not negative,
                    ),
                    InvariantCheck(
                        key="idempotency_unique",
                        expected="idempotency keys are unique",
                        actual=f"duplicate keys: {duplicate_keys}",
                        passed=not duplicate_keys,
                    ),
                ],
                affected_refs=[
                    AffectedReference(kind="lesson_unit_ledger", id=row.id)
                    for row in owner_rows
                ],
                repair_entry_points=[
                    RepairEntryPoint(label="查看课时流水", route=f"/students/{owner_id}")
                ],
                impact=ReconciliationImpact(
                    affected_lesson_units=abs(effective[-1].balance_after) if effective else 0,
                    downstream_records=len(owner_rows),
                ),
            )
        )
    return failures


def check_class_completion(db: Session, scope: RequestScope):
    sessions = db.scalars(
        select(ClassSession).where(
            ClassSession.organization_id == scope.organization_id,
            ClassSession.venue_id == scope.venue_id,
            ClassSession.status == "completed",
        )
    ).all()
    failures = []
    for session in sessions:
        records = db.scalars(
            select(AttendanceRecord).where(
                AttendanceRecord.organization_id == scope.organization_id,
                AttendanceRecord.venue_id == scope.venue_id,
                AttendanceRecord.class_session_id == session.id,
            )
        ).all()
        bad_links: list[str] = []
        for record in records:
            if record.deduct_units <= 0:
                continue
            ledger = db.scalar(
                select(LessonUnitLedger).where(
                    LessonUnitLedger.id == record.lesson_ledger_id,
                    LessonUnitLedger.organization_id == scope.organization_id,
                    LessonUnitLedger.venue_id == scope.venue_id,
                    LessonUnitLedger.status == "effective",
                )
            )
            if (
                ledger is None
                or ledger.owner_id != record.enrollment_id
                or ledger.source_type != "class_session"
                or ledger.source_id != session.id
                or ledger.delta != -record.deduct_units
            ):
                bad_links.append(record.id)
        if session.attendance_finalized_at is not None and not bad_links:
            continue
        failures.append(
            failed_result(
                scope=scope,
                rule_key="class.completion",
                rule_version=1,
                subject_type="class_session",
                subject_id=session.id,
                severity="high",
                invariants=[
                    InvariantCheck(
                        key="attendance_finalized",
                        expected="completed session has attendance_finalized_at",
                        actual=str(session.attendance_finalized_at),
                        passed=session.attendance_finalized_at is not None,
                    ),
                    InvariantCheck(
                        key="attendance_ledger_links",
                        expected="deducting attendance points to one matching effective ledger",
                        actual=f"invalid attendance ids: {bad_links}",
                        passed=not bad_links,
                    ),
                ],
                affected_refs=[
                    AffectedReference(kind="class_session", id=session.id, version=session.version),
                    *[AffectedReference(kind="attendance_record", id=item.id) for item in records],
                ],
                repair_entry_points=[
                    RepairEntryPoint(label="查看课程考勤", route=f"/classes/{session.fixed_class_id}")
                ],
                impact=ReconciliationImpact(
                    affected_lesson_units=sum(item.deduct_units for item in records),
                    downstream_records=len(records),
                ),
            )
        )
    return failures


def check_private_lesson_completion(db: Session, scope: RequestScope):
    lessons = db.scalars(
        select(PrivateLesson).where(
            PrivateLesson.organization_id == scope.organization_id,
            PrivateLesson.venue_id == scope.venue_id,
            PrivateLesson.status == "completed",
        )
    ).all()
    failures = []
    for lesson in lessons:
        package_ledgers = db.scalars(
            select(LessonUnitLedger).where(
                LessonUnitLedger.organization_id == scope.organization_id,
                LessonUnitLedger.venue_id == scope.venue_id,
                LessonUnitLedger.source_type == "private_lesson",
                LessonUnitLedger.source_id == lesson.id,
                LessonUnitLedger.status == "effective",
            )
        ).all()
        receivable_count = int(
            db.scalar(
                select(func.count(Receivable.id)).where(
                    Receivable.organization_id == scope.organization_id,
                    Receivable.venue_id == scope.venue_id,
                    Receivable.source_type == "private_lesson",
                    Receivable.source_id == lesson.id,
                )
            )
            or 0
        )
        package_ok = lesson.billing_mode != "package" or (
            len(package_ledgers) == 1
            and package_ledgers[0].owner_id == lesson.package_id
            and package_ledgers[0].delta == -1
        )
        single_ok = lesson.billing_mode != "single" or receivable_count == 1
        if package_ok and single_ok:
            continue
        failures.append(
            failed_result(
                scope=scope,
                rule_key="private_lesson.completion",
                rule_version=1,
                subject_type="private_lesson",
                subject_id=lesson.id,
                severity="high",
                invariants=[
                    InvariantCheck(
                        key="package_deduction",
                        expected="package completion has exactly one effective -1 ledger",
                        actual=f"effective ledger ids: {[item.id for item in package_ledgers]}",
                        passed=package_ok,
                    ),
                    InvariantCheck(
                        key="single_receivable",
                        expected="single lesson completion has exactly one receivable",
                        actual=f"receivable count: {receivable_count}",
                        passed=single_ok,
                    ),
                ],
                affected_refs=[
                    AffectedReference(kind="private_lesson", id=lesson.id, version=lesson.version),
                    *[
                        AffectedReference(kind="lesson_unit_ledger", id=item.id)
                        for item in package_ledgers
                    ],
                ],
                repair_entry_points=[
                    RepairEntryPoint(label="查看私教记录", route="/private-lessons")
                ],
                impact=ReconciliationImpact(
                    affected_amount=str(lesson.actual_receivable),
                    affected_lesson_units=1 if lesson.billing_mode == "package" else 0,
                    downstream_records=len(package_ledgers) + receivable_count,
                ),
            )
        )
    return failures


def check_refund_reversals(db: Session, scope: RequestScope):
    refunds = db.scalars(
        select(Refund).where(
            Refund.organization_id == scope.organization_id,
            Refund.venue_id == scope.venue_id,
            Refund.status == "void",
        )
    ).all()
    failures = []
    for refund in refunds:
        original = db.scalars(
            select(LessonUnitLedger).where(
                LessonUnitLedger.organization_id == scope.organization_id,
                LessonUnitLedger.venue_id == scope.venue_id,
                LessonUnitLedger.source_type == "refund",
                LessonUnitLedger.source_id == refund.id,
                LessonUnitLedger.change_type == "refund",
            )
        ).all()
        bad: list[str] = []
        for ledger in original:
            reversals = db.scalars(
                select(LessonUnitLedger).where(
                    LessonUnitLedger.organization_id == scope.organization_id,
                    LessonUnitLedger.venue_id == scope.venue_id,
                    LessonUnitLedger.reversal_of_id == ledger.id,
                    LessonUnitLedger.status == "effective",
                )
            ).all()
            if (
                ledger.status != "reversed"
                or len(reversals) != 1
                or reversals[0].delta != -ledger.delta
            ):
                bad.append(ledger.id)
        if not bad:
            continue
        failures.append(
            failed_result(
                scope=scope,
                rule_key="refund.reversal",
                rule_version=1,
                subject_type="refund",
                subject_id=refund.id,
                severity="critical",
                invariants=[
                    InvariantCheck(
                        key="refund_lesson_reversal",
                        expected="void refund ledgers are reversed by one matching effective ledger",
                        actual=f"invalid original ledger ids: {bad}",
                        passed=False,
                    )
                ],
                affected_refs=[
                    AffectedReference(kind="refund", id=refund.id),
                    *[AffectedReference(kind="lesson_unit_ledger", id=item.id) for item in original],
                ],
                repair_entry_points=[
                    RepairEntryPoint(label="查看退款记录", route="/finance/refunds")
                ],
                impact=ReconciliationImpact(
                    affected_amount=str(refund.actual_amount),
                    affected_lesson_units=sum(abs(item.delta) for item in original),
                    downstream_records=len(original),
                ),
            )
        )
    return failures


LESSON_RULES = (
    ReconciliationRule("ledger.chain", 1, 1, check_ledger_chains),
    ReconciliationRule("class.completion", 1, 1, check_class_completion),
    ReconciliationRule("private_lesson.completion", 1, 1, check_private_lesson_completion),
    ReconciliationRule("refund.reversal", 1, 1, check_refund_reversals),
)
