"""Tests for the pyarnes OpenAPI."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pyarnes_api.app import create_app
from pyarnes_api.routes import lifecycle as lifecycle_mod


@pytest.fixture()
def client() -> TestClient:
    """Create a fresh test client with a reset lifecycle."""
    app = create_app()
    lifecycle_mod._reset_lifecycle()
    return TestClient(app)


# ── Health ─────────────────────────────────────────────────────────────────


class TestHealth:
    """Health endpoint returns status and version."""

    def test_health(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


# ── Lifecycle ──────────────────────────────────────────────────────────────


class TestLifecycle:
    """Lifecycle endpoints manage session phases."""

    def test_get_initial_state(self, client: TestClient) -> None:
        resp = client.get("/api/v1/lifecycle")
        assert resp.status_code == 200
        data = resp.json()
        assert data["phase"] == "init"
        assert data["is_terminal"] is False

    def test_start_transition(self, client: TestClient) -> None:
        resp = client.post("/api/v1/lifecycle/transition", json={"action": "start"})
        assert resp.status_code == 200
        assert resp.json()["phase"] == "running"

    def test_full_lifecycle(self, client: TestClient) -> None:
        client.post("/api/v1/lifecycle/transition", json={"action": "start"})
        client.post("/api/v1/lifecycle/transition", json={"action": "pause"})
        client.post("/api/v1/lifecycle/transition", json={"action": "resume"})
        resp = client.post("/api/v1/lifecycle/transition", json={"action": "complete"})
        data = resp.json()
        assert data["phase"] == "completed"
        assert data["is_terminal"] is True
        assert len(data["history"]) == 4

    def test_invalid_transition(self, client: TestClient) -> None:
        # Try to complete from init (invalid)
        resp = client.post("/api/v1/lifecycle/transition", json={"action": "complete"})
        assert resp.status_code == 409

    def test_reset(self, client: TestClient) -> None:
        client.post("/api/v1/lifecycle/transition", json={"action": "start"})
        resp = client.post("/api/v1/lifecycle/reset")
        assert resp.status_code == 200
        assert resp.json()["phase"] == "init"


# ── Guardrails ─────────────────────────────────────────────────────────────


class TestGuardrails:
    """Guardrail check endpoint validates tool calls."""

    def test_allowed_call(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/guardrails/check",
            json={"tool_name": "read_file", "arguments": {"path": "/workspace/a.py"}},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

    def test_blocked_path(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/guardrails/check",
            json={"tool_name": "read_file", "arguments": {"path": "/etc/passwd"}},
        )
        data = resp.json()
        assert data["allowed"] is False
        assert "outside allowed roots" in data["violation"]

    def test_blocked_command(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/guardrails/check",
            json={"tool_name": "shell", "arguments": {"command": "sudo rm -rf /"}},
        )
        data = resp.json()
        assert data["allowed"] is False


# ── Tools ──────────────────────────────────────────────────────────────────


class TestTools:
    """Tool registry endpoints."""

    def test_list_empty(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tools")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_tool_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/tools/nonexistent")
        assert resp.status_code == 404


# ── Eval ───────────────────────────────────────────────────────────────────


class TestEval:
    """Evaluation endpoint scores scenarios."""

    def test_exact_match(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/eval",
            json={
                "suite_name": "test-suite",
                "scenarios": [
                    {"scenario": "greeting", "expected": "hello", "actual": "hello"},
                    {"scenario": "wrong", "expected": "hello", "actual": "bye"},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["passed"] == 1
        assert data["failed"] == 1
        assert data["pass_rate"] == 0.5
        assert data["average_score"] == 0.5

    def test_case_insensitive(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/eval",
            json={
                "scenarios": [
                    {"scenario": "case", "expected": "Hello", "actual": "hello"},
                ],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["results"][0]["score"] == 1.0


# ── OpenAPI spec ───────────────────────────────────────────────────────────


class TestOpenAPI:
    """OpenAPI specification is accessible."""

    def test_openapi_json(self, client: TestClient) -> None:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()
        assert spec["info"]["title"] == "pyarnes API"
        assert "/health" in spec["paths"]
        assert "/api/v1/lifecycle" in spec["paths"]
        assert "/api/v1/guardrails/check" in spec["paths"]
        assert "/api/v1/tools" in spec["paths"]
        assert "/api/v1/eval" in spec["paths"]

    def test_docs_page(self, client: TestClient) -> None:
        resp = client.get("/docs")
        assert resp.status_code == 200
