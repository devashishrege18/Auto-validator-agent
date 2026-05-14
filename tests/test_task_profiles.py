# -------------------------------------------------------
# tests/test_task_profiles.py
# -------------------------------------------------------
# Unit tests for the context-aware task classification
# and evidence scoring system.
# -------------------------------------------------------

import pytest
from validator.task_profiles import (
    classify_task, get_profile, score_evidence, TASK_PROFILES,
)


class TestClassifyTask:
    """Tests for keyword-based task classification."""

    def test_mfa_task(self):
        assert classify_task("Enable MFA for admin accounts") == "mfa"

    def test_firewall_task(self):
        assert classify_task("Check perimeter firewall status") == "firewall"

    def test_password_task(self):
        assert classify_task("Update password policy settings") == "password"

    def test_training_task(self):
        assert classify_task("Complete compliance training course") == "training"

    def test_audit_task(self):
        assert classify_task("KYC document verification review") == "audit"

    def test_unknown_defaults(self):
        assert classify_task("Do something random") == "default"

    def test_empty_string_defaults(self):
        assert classify_task("") == "default"

    def test_case_insensitive(self):
        assert classify_task("ENABLE MFA NOW") == "mfa"


class TestScoreEvidence:
    """Tests for context-aware evidence scoring."""

    def test_full_evidence_strong(self):
        evidence = {
            "api_response": True,
            "manual_status": "Done",
            "document_id": "DOC-1",
            "screenshot_uploaded": True,
            "reviewer": "Amit",
        }
        result = score_evidence(evidence, "mfa")
        assert result["evidence_quality"] == "strong"
        assert result["weighted_score"] >= 0.7

    def test_empty_evidence_weak(self):
        result = score_evidence({}, "firewall")
        assert result["evidence_quality"] == "weak"
        assert result["weighted_score"] == 0

    def test_api_only_for_mfa_moderate(self):
        evidence = {"api_response": True}
        result = score_evidence(evidence, "mfa")
        assert result["weighted_score"] >= 0.5  # API is 70% for MFA

    def test_category_in_result(self):
        result = score_evidence({}, "training")
        assert result["category"] == "training"

    def test_all_profiles_have_weights(self):
        for name, profile in TASK_PROFILES.items():
            assert "weights" in profile
            assert "min_confidence" in profile
