from fastapi.testclient import TestClient


def test_runtime_openapi_has_dashboard_report_and_audit_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/dashboard" in paths
    assert "/api/v1/reports/operations" in paths
    assert "/api/v1/audit" in paths
    assert "/api/v1/audit/entities/{entity_type}/{entity_id}" in paths
    assert "/api/v1/audit/requests/{request_id}" in paths
