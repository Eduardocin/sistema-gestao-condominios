import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


def test_health_does_not_require_database(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_exposes_versioned_health_in_openapi(client):
    assert "/api/v1/health" in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_cors_allows_local_frontend(client, origin):
    response = client.options(
        "/api/v1/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_external_origin(client):
    response = client.options(
        "/api/v1/health",
        headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_missing_route_returns_consistent_error(client):
    response = client.get("/api/v1/missing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "http_error"


def test_unexpected_error_does_not_leak_details():
    app = create_app()
    router = APIRouter()

    @router.get("/failure")
    def failure():
        raise RuntimeError("private database credentials")

    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/failure", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "private database credentials" not in response.text
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_validation_error_does_not_reflect_private_input():
    app = create_app()

    @app.get("/validation-probe")
    def validation_probe(value: int):
        return {"value": value}

    with TestClient(app) as client:
        response = client.get("/validation-probe", params={"value": "private-input"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "private-input" not in response.text
