from fastapi.testclient import TestClient


def test_runtime_openapi_has_schedule_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/schedule" in paths
    assert "/api/v1/schedule/conflicts:check" in paths
