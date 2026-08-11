from fastapi.testclient import TestClient

from shuttlecube.domain.identity.models import SystemUser


def test_login_session_logout(client: TestClient, admin: SystemUser) -> None:
    logged = client.post(
        "/api/v1/session/login", json={"username": admin.username, "password": "password123"}
    )
    assert logged.status_code == 200
    csrf = logged.json()["csrf_token"]
    assert client.get("/api/v1/session").json()["display_name"] == "聂老板"
    assert client.post("/api/v1/session/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/v1/session").status_code == 401
