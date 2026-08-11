from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select

from shuttlecube.application.queries.operations_report import get_operations_report
from shuttlecube.domain.audit.models import AuditLog
from shuttlecube.domain.finance.models import OtherIncome


def test_other_income_is_idempotent_audited_and_included_in_report(authenticated, db) -> None:
    client, headers = authenticated
    payload = {
        "category": "drinks",
        "received_at": datetime(2026, 8, 4, 10, tzinfo=UTC).isoformat(),
        "amount": "75.00",
        "payer": "散客",
        "payment_method": "wechat",
        "notes": "饮料和水",
    }
    write_headers = {**headers, "Idempotency-Key": "other-income-1"}

    first = client.post("/api/v1/other-incomes", json=payload, headers=write_headers)
    repeated = client.post("/api/v1/other-incomes", json=payload, headers=write_headers)
    assert first.status_code == repeated.status_code == 201
    assert first.json()["id"] == repeated.json()["id"]
    assert db.query(OtherIncome).count() == 1

    report = get_operations_report(db, date(2026, 8, 1), date(2026, 8, 31))
    assert report["income"] == Decimal("75.00")
    assert report["income_by_source"] == {"other_income": Decimal("75.00")}
    audit = db.scalar(select(AuditLog).where(AuditLog.action_type == "other_income.created"))
    assert audit is not None

    voided = client.post(
        f"/api/v1/other-incomes/{first.json()['id']}/void",
        json={"reason": "重复登记"},
        headers=headers,
    )
    assert voided.status_code == 200
    assert get_operations_report(db, date(2026, 8, 1), date(2026, 8, 31))["income"] == Decimal("0.00")
