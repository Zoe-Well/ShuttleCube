from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shuttlecube.domain.finance.models import Receivable


def test_runtime_openapi_has_complete_finance_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/receivables" in paths
    assert "/api/v1/receivables/{receivable_id}" in paths
    assert "/api/v1/receivables/{receivable_id}/payments" in paths
    assert "/api/v1/receivables/{receivable_id}/refunds" in paths
    assert "/api/v1/payments/{payment_id}/void" in paths
    assert "/api/v1/refunds/{refund_id}/void" in paths
    assert "/api/v1/expenses" in paths
    assert "/api/v1/expenses/{expense_id}/void" in paths
    assert "/api/v1/attachments/{attachment_id}/content" in paths


def test_attachment_content_requires_login(client: TestClient) -> None:
    response = client.get("/api/v1/attachments/missing/content")
    assert response.status_code == 401


def test_record_payment_returns_latest_receivable_summary(
    authenticated: tuple[TestClient, dict[str, str]], db: Session
) -> None:
    client, headers = authenticated
    item = Receivable(
        source_type="other",
        source_id="contract-source",
        suggested_amount=Decimal("80.00"),
        actual_amount=Decimal("80.00"),
    )
    db.add(item)
    db.commit()

    response = client.post(
        f"/api/v1/receivables/{item.id}/payments",
        headers={**headers, "Idempotency-Key": "contract-payment"},
        json={
            "paid_at": "2026-08-04T10:00:00+08:00",
            "amount": "30.00",
            "method": "wechat",
        },
    )
    assert response.status_code == 201
    assert response.json()["received_amount"] == 30.0
    assert response.json()["outstanding_amount"] == 50.0
