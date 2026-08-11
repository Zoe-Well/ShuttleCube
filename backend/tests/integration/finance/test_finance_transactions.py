from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from shuttlecube.api.errors import BusinessError
from shuttlecube.application.commands.attachments import delete_attachment, upload_attachment
from shuttlecube.application.commands.attendance import balance
from shuttlecube.application.commands.expenses import create_expense
from shuttlecube.application.commands.payments import record_payment
from shuttlecube.application.commands.refunds import record_refund, void_refund
from shuttlecube.application.queries.receivables import receivable_summary
from shuttlecube.domain.classes.enrollment_models import LessonUnitLedger
from shuttlecube.domain.finance.models import Payment, Receivable, Refund
from shuttlecube.domain.private_lessons.models import PrivateLessonPackage
from shuttlecube.infrastructure.artifacts.local import LocalObjectStorage


def receivable(db: Session, amount: str = "100.00") -> Receivable:
    item = Receivable(
        source_type="other",
        source_id="source-1",
        suggested_amount=Decimal(amount),
        actual_amount=Decimal(amount),
    )
    db.add(item)
    db.commit()
    return item


def test_split_payment_refund_and_expense_remain_consistent(db: Session, admin) -> None:
    item = receivable(db)
    now = datetime(2026, 8, 4, tzinfo=UTC)

    first = record_payment(
        db,
        item,
        paid_at=now,
        amount=Decimal("60.00"),
        method="wechat",
        payer_name="家长",
        received_by=None,
        notes=None,
        actor_id=admin.id,
        idempotency_key="payment-1",
        request_id="request-1",
    )
    repeated = record_payment(
        db,
        item,
        paid_at=now,
        amount=Decimal("60.00"),
        method="wechat",
        payer_name="家长",
        received_by=None,
        notes=None,
        actor_id=admin.id,
        idempotency_key="payment-1",
        request_id="request-1",
    )
    assert repeated.id == first.id

    record_payment(
        db,
        item,
        paid_at=now,
        amount=Decimal("40.00"),
        method="cash",
        payer_name=None,
        received_by=None,
        notes=None,
        actor_id=admin.id,
        idempotency_key="payment-2",
        request_id="request-2",
    )
    record_refund(
        db,
        item,
        payment_id=first.id,
        refunded_at=now,
        suggested_amount=Decimal("25.00"),
        actual_amount=Decimal("25.00"),
        reason="退还部分课程",
        lesson_units_to_remove=0,
        actor_id=admin.id,
        idempotency_key="refund-1",
        request_id="request-3",
    )
    expense = create_expense(
        db,
        category="equipment",
        spent_at=now,
        amount=Decimal("20.00"),
        payee="器材商",
        payment_method="bank",
        source_type=None,
        source_id=None,
        notes=None,
        actor_id=admin.id,
        idempotency_key="expense-1",
        request_id="request-4",
    )

    summary = receivable_summary(db, item)
    assert summary.actual_amount == Decimal("75.00")
    assert summary.received_amount == Decimal("100.00")
    assert summary.refunded_amount == Decimal("25.00")
    assert summary.outstanding_amount == Decimal("0.00")
    assert summary.payment_status == "partially_refunded"
    assert expense.amount == Decimal("20.00")
    assert db.query(Payment).count() == 2
    assert db.query(Refund).count() == 1


def test_payment_and_refund_limits_are_enforced(db: Session, admin) -> None:
    item = receivable(db)
    now = datetime(2026, 8, 4, tzinfo=UTC)
    with pytest.raises(BusinessError) as overpayment:
        record_payment(
            db,
            item,
            paid_at=now,
            amount=Decimal("100.01"),
            method="cash",
            payer_name=None,
            received_by=None,
            notes=None,
            actor_id=admin.id,
            idempotency_key="overpayment",
            request_id="request-overpayment",
        )
    assert overpayment.value.code == "payment_exceeds_outstanding"

    record_payment(
        db,
        item,
        paid_at=now,
        amount=Decimal("50.00"),
        method="cash",
        payer_name=None,
        received_by=None,
        notes=None,
        actor_id=admin.id,
        idempotency_key="valid-payment",
        request_id="request-payment",
    )
    with pytest.raises(BusinessError) as excessive_refund:
        record_refund(
            db,
            item,
            payment_id=None,
            refunded_at=now,
            suggested_amount=None,
            actual_amount=Decimal("50.01"),
            reason="超额退款",
            lesson_units_to_remove=0,
            actor_id=admin.id,
            idempotency_key="excessive-refund",
            request_id="request-refund",
        )
    assert excessive_refund.value.code == "refund_exceeds_available"


def test_void_refund_restores_lesson_units_and_entitlement_status(db: Session, admin) -> None:
    now = datetime(2026, 8, 4, tzinfo=UTC)
    package = PrivateLessonPackage(
        student_id="student-1",
        bound_coach_id="coach-1",
        purchased_units=2,
        unit_price=Decimal("50.00"),
        actual_receivable=Decimal("100.00"),
        status="active",
    )
    db.add(package)
    db.flush()
    item = Receivable(
        source_type="private_package",
        source_id=package.id,
        suggested_amount=Decimal("100.00"),
        actual_amount=Decimal("100.00"),
    )
    db.add(item)
    db.flush()
    db.add(
        LessonUnitLedger(
            owner_type="private_package",
            owner_id=package.id,
            change_type="purchase",
            delta=2,
            balance_before=0,
            balance_after=2,
            source_type="private_package",
            source_id=package.id,
            operated_by=admin.id,
            operated_at=now,
            idempotency_key="refund-void-initial-units",
        )
    )
    db.commit()
    record_payment(
        db,
        item,
        paid_at=now,
        amount=Decimal("100.00"),
        method="wechat",
        payer_name=None,
        received_by=None,
        notes=None,
        actor_id=admin.id,
        idempotency_key="refund-void-payment",
        request_id="refund-void-payment-request",
    )
    refund = record_refund(
        db,
        item,
        payment_id=None,
        refunded_at=now,
        suggested_amount=Decimal("100.00"),
        actual_amount=Decimal("100.00"),
        reason="退回整包",
        lesson_units_to_remove=2,
        actor_id=admin.id,
        idempotency_key="refund-void-refund",
        request_id="refund-void-refund-request",
    )

    assert balance(db, package.id) == 0
    assert package.status == "refunded"

    void_refund(
        db,
        refund,
        reason="退款登记错误",
        actor_id=admin.id,
        request_id="refund-void-request",
    )

    assert balance(db, package.id) == 2
    assert package.status == "active"
    refund_ledger = db.query(LessonUnitLedger).filter_by(source_id=refund.id).first()
    assert refund_ledger is not None
    assert refund_ledger.status == "reversed"
    reversed_ledger = db.query(LessonUnitLedger).filter_by(reversal_of_id=refund_ledger.id).one()
    assert reversed_ledger.delta == 2
    assert reversed_ledger.balance_after == 2


def test_private_attachment_is_validated_and_soft_deleted(db: Session, admin, tmp_path) -> None:
    item = receivable(db)
    payment = record_payment(
        db,
        item,
        paid_at=datetime(2026, 8, 4, tzinfo=UTC),
        amount=Decimal("10.00"),
        method="cash",
        payer_name=None,
        received_by=None,
        notes=None,
        actor_id=admin.id,
        idempotency_key="attachment-payment",
        request_id="attachment-payment-request",
    )
    storage = LocalObjectStorage(tmp_path)
    attachment = upload_attachment(
        db,
        storage,
        owner_type="payment",
        owner_id=payment.id,
        original_filename="receipt.png",
        media_type="image/png",
        content=b"private-image",
        actor_id=admin.id,
        request_id="attachment-upload",
    )
    content, media_type = storage.get(attachment.storage_key)
    assert content == b"private-image"
    assert media_type == "image/png"

    delete_attachment(
        db,
        attachment,
        actor_id=admin.id,
        reason="上传错误",
        request_id="attachment-delete",
    )
    assert attachment.status == "deleted"
