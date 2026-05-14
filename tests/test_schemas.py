# -------------------------------------------------------
# tests/test_schemas.py
# -------------------------------------------------------
# Unit tests for Pydantic models in validator/schemas.py.
#
# Tests cover:
#   - Valid model creation
#   - Default values for optional fields
#   - Type validation (wrong types should raise errors)
#   - ReasoningRequest/Response models
# -------------------------------------------------------

import pytest
from pydantic import ValidationError
from validator.schemas import (
    Evidence,
    ComplianceTask,
    ValidationResult,
    ReasoningRequest,
    ReasoningResponse,
)


# -------------------------------------------------------
# Evidence Model Tests
# -------------------------------------------------------

class TestEvidence:
    """Tests for the Evidence Pydantic model."""

    def test_evidence_all_fields(self):
        """All fields provided should populate correctly."""
        e = Evidence(
            document_id="DOC-1234",
            submitted_at="2026-01-15T10:00:00Z",
            reviewer="Amit Verma",
        )
        assert e.document_id == "DOC-1234"
        assert e.submitted_at == "2026-01-15T10:00:00Z"
        assert e.reviewer == "Amit Verma"

    def test_evidence_defaults_to_none(self):
        """All fields are optional and default to None."""
        e = Evidence()
        assert e.document_id is None
        assert e.submitted_at is None
        assert e.reviewer is None

    def test_evidence_partial_fields(self):
        """Some fields provided, others should default to None."""
        e = Evidence(document_id="DOC-999")
        assert e.document_id == "DOC-999"
        assert e.reviewer is None


# -------------------------------------------------------
# ComplianceTask Model Tests
# -------------------------------------------------------

class TestComplianceTask:
    """Tests for the ComplianceTask Pydantic model."""

    def test_valid_task(self):
        """A fully valid task should be created without errors."""
        task = ComplianceTask(
            task_id="TASK-001",
            title="KYC Verification",
            department="Compliance",
            assigned_to="Rahul S.",
            status="completed",
            evidence=Evidence(document_id="DOC-001"),
        )
        assert task.task_id == "TASK-001"
        assert task.status == "completed"

    def test_missing_required_field_raises(self):
        """Missing a required field should raise ValidationError."""
        with pytest.raises(ValidationError):
            ComplianceTask(
                task_id="TASK-001",
                # title is missing
                department="Compliance",
                assigned_to="Rahul S.",
                status="completed",
                evidence=Evidence(),
            )

    def test_evidence_nested_correctly(self):
        """Evidence should be accessible as a nested object."""
        task = ComplianceTask(
            task_id="TASK-002",
            title="AML Review",
            department="Risk",
            assigned_to="Priya K.",
            status="in_progress",
            evidence=Evidence(reviewer="Inspector"),
        )
        assert task.evidence.reviewer == "Inspector"
        assert task.evidence.document_id is None


# -------------------------------------------------------
# ValidationResult Model Tests
# -------------------------------------------------------

class TestValidationResult:
    """Tests for the ValidationResult output model."""

    def test_valid_result(self):
        """A valid result should populate all fields."""
        result = ValidationResult(
            task_id="TASK-001",
            title="KYC Check",
            verdict="PASS",
            reasons=["All evidence present."],
            validated_at="2026-05-14T10:00:00Z",
        )
        assert result.verdict == "PASS"
        assert len(result.reasons) == 1

    def test_multiple_reasons(self):
        """Results can have multiple reason strings."""
        result = ValidationResult(
            task_id="TASK-002",
            title="AML Review",
            verdict="FAIL",
            reasons=["Missing document_id", "Missing reviewer"],
            validated_at="2026-05-14T10:00:00Z",
        )
        assert len(result.reasons) == 2


# -------------------------------------------------------
# ReasoningRequest Model Tests
# -------------------------------------------------------

class TestReasoningRequest:
    """Tests for the ReasoningRequest input model."""

    def test_valid_request(self):
        """A valid request should parse correctly."""
        req = ReasoningRequest(
            task_id=1,
            task="Enable MFA",
            evidence={"api_response": True},
        )
        assert req.task_id == 1
        assert req.evidence["api_response"] is True

    def test_default_task_id(self):
        """task_id should default to 1."""
        req = ReasoningRequest(
            task="Some task",
            evidence={},
        )
        assert req.task_id == 1

    def test_empty_evidence(self):
        """Empty evidence dict should be valid."""
        req = ReasoningRequest(task="Test task", evidence={})
        assert req.evidence == {}


# -------------------------------------------------------
# ReasoningResponse Model Tests
# -------------------------------------------------------

class TestReasoningResponse:
    """Tests for the ReasoningResponse output model."""

    def test_valid_response(self):
        """Full response with all fields."""
        resp = ReasoningResponse(
            task_id=1,
            status="VERIFIED",
            confidence_score=95,
            risk_score=5,
            reason="All evidence checks out.",
            concerns=[],
            recommendation="No action needed.",
            suspicion_flags=[],
            llm_used=True,
            llm_model="phi3",
            timestamp="2026-05-14T10:00:00Z",
        )
        assert resp.status == "VERIFIED"
        assert resp.llm_used is True

    def test_defaults(self):
        """Optional fields should have sensible defaults."""
        resp = ReasoningResponse(
            task_id=1,
            status="NEEDS_REVIEW",
            confidence_score=50,
            risk_score=30,
            reason="Uncertain.",
        )
        assert resp.concerns == []
        assert resp.suspicion_flags == []
        assert resp.llm_used is False
        assert resp.llm_model is None
