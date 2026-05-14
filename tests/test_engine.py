# -------------------------------------------------------
# tests/test_engine.py
# -------------------------------------------------------
# Unit tests for the rule-based validation engine
# (validator/engine.py).
#
# Tests cover all 3 verdict paths:
#   - PASS:         status=completed + full evidence
#   - FAIL:         status=completed + missing evidence
#   - NEEDS_REVIEW: status != completed
# -------------------------------------------------------

import pytest
from validator.schemas import ComplianceTask, Evidence
from validator.engine import validate_task


# -------------------------------------------------------
# Helper — quickly build a ComplianceTask for testing
# -------------------------------------------------------

def make_task(
    status="completed",
    document_id="DOC-001",
    submitted_at="2026-01-15",
    reviewer="Tester",
):
    """Create a ComplianceTask with configurable fields."""
    return ComplianceTask(
        task_id="TEST-001",
        title="Test Task",
        department="Testing",
        assigned_to="Test User",
        status=status,
        evidence=Evidence(
            document_id=document_id,
            submitted_at=submitted_at,
            reviewer=reviewer,
        ),
    )


# -------------------------------------------------------
# PASS Verdict Tests
# -------------------------------------------------------

class TestPassVerdict:
    """Tasks marked completed with full evidence should PASS."""

    def test_full_evidence_passes(self):
        """All 3 evidence fields present → PASS."""
        task = make_task()
        result = validate_task(task)
        assert result.verdict == "PASS"

    def test_pass_has_task_id(self):
        """Result should carry the original task_id."""
        task = make_task()
        result = validate_task(task)
        assert result.task_id == "TEST-001"

    def test_pass_has_timestamp(self):
        """Result should include a validated_at timestamp."""
        task = make_task()
        result = validate_task(task)
        assert result.validated_at is not None
        assert len(result.validated_at) > 0

    def test_pass_reasons_explain_success(self):
        """PASS reasons should mention validation passed."""
        task = make_task()
        result = validate_task(task)
        assert any("passed" in r.lower() for r in result.reasons)


# -------------------------------------------------------
# FAIL Verdict Tests
# -------------------------------------------------------

class TestFailVerdict:
    """Tasks marked completed but with missing evidence should FAIL."""

    def test_missing_document_id_fails(self):
        """Missing document_id → FAIL."""
        task = make_task(document_id=None)
        result = validate_task(task)
        assert result.verdict == "FAIL"

    def test_missing_submitted_at_fails(self):
        """Missing submitted_at → FAIL."""
        task = make_task(submitted_at=None)
        result = validate_task(task)
        assert result.verdict == "FAIL"

    def test_missing_reviewer_fails(self):
        """Missing reviewer → FAIL."""
        task = make_task(reviewer=None)
        result = validate_task(task)
        assert result.verdict == "FAIL"

    def test_all_evidence_missing_fails(self):
        """All evidence fields missing → FAIL."""
        task = make_task(document_id=None, submitted_at=None, reviewer=None)
        result = validate_task(task)
        assert result.verdict == "FAIL"

    def test_fail_reasons_list_missing_fields(self):
        """FAIL reasons should mention which fields are missing."""
        task = make_task(document_id=None, reviewer=None)
        result = validate_task(task)
        assert any("document_id" in r for r in result.reasons)
        assert any("reviewer" in r for r in result.reasons)


# -------------------------------------------------------
# NEEDS_REVIEW Verdict Tests
# -------------------------------------------------------

class TestNeedsReviewVerdict:
    """Tasks not marked completed should get NEEDS_REVIEW."""

    def test_in_progress_needs_review(self):
        """status='in_progress' → NEEDS_REVIEW."""
        task = make_task(status="in_progress")
        result = validate_task(task)
        assert result.verdict == "NEEDS_REVIEW"

    def test_pending_needs_review(self):
        """status='pending' → NEEDS_REVIEW."""
        task = make_task(status="pending")
        result = validate_task(task)
        assert result.verdict == "NEEDS_REVIEW"

    def test_unknown_status_needs_review(self):
        """Any non-completed status → NEEDS_REVIEW."""
        task = make_task(status="unknown_status")
        result = validate_task(task)
        assert result.verdict == "NEEDS_REVIEW"

    def test_review_ignores_evidence(self):
        """Even with full evidence, non-completed status → NEEDS_REVIEW."""
        task = make_task(status="pending")
        result = validate_task(task)
        assert result.verdict == "NEEDS_REVIEW"
