from fastapi.testclient import TestClient


def test_runtime_openapi_has_class_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/classes" in paths
    assert "/api/v1/makeups" not in paths
