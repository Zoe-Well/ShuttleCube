from fastapi.testclient import TestClient


def test_runtime_openapi_has_payroll_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/coach-fees" in paths
    assert "/api/v1/coach-fees/{fee_id}" in paths
    assert "/api/v1/payroll-settlements" in paths
    assert "/api/v1/payroll-settlements/{settlement_id}" in paths
    assert "/api/v1/payroll-settlements/{settlement_id}/void" in paths
