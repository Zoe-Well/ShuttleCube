from fastapi.testclient import TestClient


def test_runtime_openapi_has_operation_routes(client: TestClient) -> None:
    p = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/schedule/bulk-delete" in p
    assert "delete" in p["/api/v1/schedule/{schedule_id}"]
    assert "/api/v1/private-lessons" in p
    assert "/api/v1/venue-bookings" in p
    assert "/api/v1/events" in p
    assert "/api/v1/private-lessons/bulk-cancel" in p
    assert "/api/v1/private-lessons/bulk-delete" in p
    assert "delete" in p["/api/v1/private-lessons/{lesson_id}"]
    assert "/api/v1/venue-bookings/bulk-cancel" in p
    assert "/api/v1/venue-bookings/bulk-delete" in p
    assert "delete" in p["/api/v1/venue-bookings/{booking_id}"]
    assert "/api/v1/venue-bookings/{booking_id}/reschedule" in p
    assert "/api/v1/events/bulk-cancel" in p
    assert "/api/v1/events/bulk-delete" in p
    assert "delete" in p["/api/v1/events/{event_id}"]
    assert "/api/v1/events/{event_id}/reschedule" in p


def test_foundational_operations_routes_are_exposed_with_stable_operation_ids(
    client: TestClient,
) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/v1/operations/context": {"get": "getOperationsContext"},
        "/api/v1/operations/settings/model": {
            "get": "getOperationsModelSetting",
            "patch": "updateOperationsModelSetting",
        },
        "/api/v1/operations/policies": {
            "get": "listOperationsPolicies",
            "post": "createOperationsPolicyDraft",
        },
        "/api/v1/operations/policies/{policy_id}:activate": {
            "post": "activateOperationsPolicy"
        },
        "/api/v1/operations/runs/{run_id}": {"get": "getOperationRun"},
        "/api/v1/operations/runs/{run_id}/events": {
            "get": "listOperationRunEvents"
        },
    }

    for path, methods in expected.items():
        assert path in paths
        for method, operation_id in methods.items():
            assert paths[path][method]["operationId"] == operation_id


def test_operations_contract_never_exposes_provider_credentials(client: TestClient) -> None:
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    setting = schemas["ModelSetting"]

    assert set(setting["required"]) == {
        "model_enabled",
        "provider_configured",
        "updated_at",
        "version",
    }
    assert not {
        "api_key",
        "secret",
        "credential",
        "organization_id",
        "venue_id",
    } & set(setting["properties"])


def test_unauthenticated_operations_response_is_rfc_problem(client: TestClient) -> None:
    response = client.get("/api/v1/operations/context")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body.keys() >= {"type", "title", "status", "detail", "instance"}
    assert body["status"] == 401
    assert body["title"] == "unauthenticated"
    assert body["instance"] == "/api/v1/operations/context"


def test_authenticated_user_without_reviewed_membership_gets_safe_problem(
    authenticated: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ = authenticated
    response = client.get("/api/v1/operations/context")

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "membership_review_required"
