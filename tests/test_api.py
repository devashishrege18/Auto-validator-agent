# -------------------------------------------------------
# tests/test_api.py
# -------------------------------------------------------
# Integration tests for FastAPI endpoints using TestClient.
#
# These tests call the actual API routes and verify the
# response status codes, JSON structure, and business logic.
#
# TestClient runs the app in-process — no server needed.
# -------------------------------------------------------

import pytest
from fastapi.testclient import TestClient
from main import app


# -------------------------------------------------------
# Create the test client (used by all tests)
# -------------------------------------------------------
client = TestClient(app)


# -------------------------------------------------------
# Health Check
# -------------------------------------------------------

class TestHealthCheck:
    """Tests for the root / endpoint."""

    def test_root_returns_200(self):
        """GET / should return 200."""
        response = client.get("/")
        assert response.status_code == 200

    def test_root_has_message(self):
        """Root response should have a 'message' field."""
        data = client.get("/").json()
        assert "message" in data


# -------------------------------------------------------
# Mock Compliance API Endpoints
# -------------------------------------------------------

class TestMockAPIs:
    """Tests for /mfa-status, /firewall-status, /password-policy."""

    def test_mfa_status_returns_200(self):
        response = client.get("/mfa-status")
        assert response.status_code == 200

    def test_mfa_has_enabled_field(self):
        data = client.get("/mfa-status").json()
        assert "mfa_enabled" in data
        assert isinstance(data["mfa_enabled"], bool)

    def test_firewall_status_returns_200(self):
        response = client.get("/firewall-status")
        assert response.status_code == 200

    def test_firewall_has_active_field(self):
        data = client.get("/firewall-status").json()
        assert "firewall_active" in data
        assert isinstance(data["firewall_active"], bool)

    def test_password_policy_returns_200(self):
        response = client.get("/password-policy")
        assert response.status_code == 200

    def test_password_policy_structure(self):
        data = client.get("/password-policy").json()
        assert "minimum_length" in data
        assert "special_characters_required" in data
        assert isinstance(data["minimum_length"], int)


# -------------------------------------------------------
# Tasks Endpoints
# -------------------------------------------------------

class TestTasksEndpoints:
    """Tests for /tasks and /tasks/{task_id}."""

    def test_list_tasks_returns_200(self):
        response = client.get("/tasks")
        assert response.status_code == 200

    def test_list_tasks_returns_list(self):
        data = client.get("/tasks").json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_task_has_required_fields(self):
        """Each task should have id, title, status, etc."""
        tasks = client.get("/tasks").json()
        task = tasks[0]
        assert "task_id" in task
        assert "title" in task
        assert "status" in task

    def test_get_single_task(self):
        """GET /tasks/TASK-001 should return that specific task."""
        response = client.get("/tasks/TASK-001")
        assert response.status_code == 200
        assert response.json()["task_id"] == "TASK-001"

    def test_invalid_task_returns_404(self):
        """GET /tasks/NONEXISTENT should return 404."""
        response = client.get("/tasks/NONEXISTENT")
        assert response.status_code == 404


# -------------------------------------------------------
# Validation Endpoints
# -------------------------------------------------------

class TestValidationEndpoints:
    """Tests for /validate/{task_id} and /validate/all."""

    def test_validate_single_task(self):
        """Validating a known task should return a result."""
        response = client.get("/validate/TASK-001")
        assert response.status_code == 200
        data = response.json()
        assert "verdict" in data
        assert data["verdict"] in ("PASS", "FAIL", "NEEDS_REVIEW")

    def test_validate_all_returns_list(self):
        """GET /validate/all should return a list of results."""
        response = client.get("/validate/all")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_validate_all_has_verdicts(self):
        """Each result in validate/all should have a verdict."""
        results = client.get("/validate/all").json()
        for result in results:
            assert result["verdict"] in ("PASS", "FAIL", "NEEDS_REVIEW")


# -------------------------------------------------------
# Audit Endpoint
# -------------------------------------------------------

class TestAuditEndpoint:
    """Tests for GET /audit (infrastructure compliance check)."""

    def test_audit_returns_200(self):
        response = client.get("/audit")
        assert response.status_code == 200

    def test_audit_has_overall_status(self):
        data = client.get("/audit").json()
        assert "overall" in data

    def test_audit_has_checks(self):
        data = client.get("/audit").json()
        assert "checks" in data
        assert isinstance(data["checks"], list)
        assert len(data["checks"]) == 3  # MFA, Firewall, Password

    def test_audit_checks_have_verdict(self):
        """Each check should have check name, verdict, details."""
        checks = client.get("/audit").json()["checks"]
        for check in checks:
            assert "check" in check
            assert "verdict" in check
            assert "details" in check

    def test_audit_has_summary(self):
        data = client.get("/audit").json()
        assert "summary" in data
        summary = data["summary"]
        assert "total_checks" in summary
        assert "verified" in summary
        assert "non_compliant" in summary


# -------------------------------------------------------
# Reasoning Validate Endpoint
# -------------------------------------------------------

class TestReasoningEndpoint:
    """Tests for POST /reasoning-validate."""

    def test_valid_request_returns_200(self):
        """A properly formed request should return 200."""
        payload = {
            "task_id": 1,
            "task": "Enable MFA for admin accounts",
            "evidence": {
                "api_response": True,
                "manual_status": "Done",
            },
        }
        response = client.post("/reasoning-validate", json=payload)
        assert response.status_code == 200

    def test_response_has_verdict_fields(self):
        """Response should contain status, confidence, risk, reason."""
        payload = {
            "task_id": 1,
            "task": "Test task",
            "evidence": {"api_response": True},
        }
        data = client.post("/reasoning-validate", json=payload).json()
        assert "status" in data
        assert "confidence_score" in data
        assert "risk_score" in data
        assert "reason" in data

    def test_status_is_valid_enum(self):
        """Status should be one of VERIFIED/NON_COMPLIANT/NEEDS_REVIEW."""
        payload = {
            "task_id": 1,
            "task": "Check firewall",
            "evidence": {"api_response": False, "manual_status": "Done"},
        }
        data = client.post("/reasoning-validate", json=payload).json()
        assert data["status"] in ("VERIFIED", "NON_COMPLIANT", "NEEDS_REVIEW")

    def test_empty_evidence_returns_result(self):
        """Even empty evidence should return a result, not crash."""
        payload = {
            "task_id": 99,
            "task": "Unknown task",
            "evidence": {},
        }
        response = client.post("/reasoning-validate", json=payload)
        assert response.status_code == 200

    def test_missing_task_field_returns_422(self):
        """Missing required 'task' field → 422 validation error."""
        payload = {"evidence": {}}
        response = client.post("/reasoning-validate", json=payload)
        assert response.status_code == 422
