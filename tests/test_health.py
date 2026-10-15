"""Tests for application health check endpoints."""

from unittest.mock import patch
from fastapi.testclient import TestClient


def test_root_health_endpoint(client: TestClient):
    """Verify GET /health returns 200 and healthy database status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["environment"] == "development"
    assert data["version"] == "0.1.0"


def test_api_v1_health_endpoint(client: TestClient):
    """Verify GET /api/v1/health returns 200 and matching payload."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_health_endpoint_reports_unhealthy_when_database_down(client: TestClient):
    """Verify health endpoint returns 503 and 'disconnected' when DB connection check fails."""
    with patch("app.main.check_database_connection", return_value=False):
        response = client.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"

    with patch("app.api.v1.endpoints.health.check_database_connection", return_value=False):
        response = client.get("/api/v1/health")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
