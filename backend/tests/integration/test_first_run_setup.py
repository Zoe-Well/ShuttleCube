from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shuttlecube.config import Settings, get_settings
from shuttlecube.domain.identity.models import SystemUser
from shuttlecube.domain.scheduling.court import Court, Venue


def test_first_run_setup_is_not_exposed_in_server_mode(client: TestClient) -> None:
    payload = {
        "venue_name": "测试球馆",
        "court_count": 3,
        "username": "owner",
        "display_name": "店长",
        "password": "password123",
    }
    assert client.get("/api/v1/setup/status").json() == {
        "required": False,
        "desktop_mode": False,
    }
    assert client.post("/api/v1/setup", json=payload).status_code == 409


def test_first_run_setup_creates_admin_venue_and_courts(client: TestClient, db: Session) -> None:
    client.app.dependency_overrides[get_settings] = lambda: Settings(desktop_mode=True)
    assert client.get("/api/v1/setup/status").json()["required"] is True
    payload = {
        "venue_name": "测试球馆",
        "court_count": 3,
        "username": "owner",
        "display_name": "店长",
        "password": "password123",
    }
    response = client.post("/api/v1/setup", json=payload)

    assert response.status_code == 201
    assert response.json()["username"] == "owner"
    assert db.query(SystemUser).count() == 1
    assert db.query(Venue).one().name == "测试球馆"
    assert [court.code for court in db.query(Court).order_by(Court.code)] == ["1", "2", "3"]
    assert client.get("/api/v1/session").status_code == 200
    assert client.post("/api/v1/setup", json=payload).status_code == 409
