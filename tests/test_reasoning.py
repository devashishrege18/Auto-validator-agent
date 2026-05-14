# -------------------------------------------------------
# tests/test_reasoning.py
# -------------------------------------------------------
# Unit tests for the reasoning engine's deterministic
# layers (validator/reasoning_engine.py).
#
# Tests cover:
#   - Suspicion detection (7 patterns)
#   - Risk score calculation
#   - Confidence score calculation
#   - Deterministic verdict generation
#
# NOTE: LLM-dependent functions (call_ollama, etc.) are
# NOT tested here — they require a running Ollama server.
# The deterministic fallback path IS fully tested.
# -------------------------------------------------------

import pytest
from validator.reasoning_engine import (
    detect_suspicions,
    calculate_risk_score,
    calculate_confidence,
    deterministic_verdict,
    VERIFIED,
    NON_COMPLIANT,
    NEEDS_REVIEW,
)


# -------------------------------------------------------
# Suspicion Detection Tests
# -------------------------------------------------------

class TestSuspicionDetection:
    """Tests for detect_suspicions() — the deterministic rules."""

    def test_no_evidence_flags_correctly(self):
        """Empty evidence should trigger NO_EVIDENCE flag."""
        flags = detect_suspicions("Enable MFA", {})
        flag_names = [f["flag"] for f in flags]
        assert "NO_EVIDENCE" in flag_names

    def test_clean_evidence_no_flags(self):
        """Full corroborating evidence should produce no flags."""
        evidence = {
            "api_response": True,
            "manual_status": "Done",
            "screenshot_uploaded": True,
            "reviewer": "Amit",
            "document_id": "DOC-001",
        }
        flags = detect_suspicions("Enable MFA", evidence)
        assert len(flags) == 0

    def test_contradiction_detected(self):
        """API=False + manual='Done' is a contradiction."""
        evidence = {
            "api_response": False,
            "manual_status": "Done",
        }
        flags = detect_suspicions("Activate firewall", evidence)
        flag_names = [f["flag"] for f in flags]
        assert "CONTRADICTORY_EVIDENCE" in flag_names

    def test_manual_without_api(self):
        """Manual='Done' but no API check → suspicious."""
        evidence = {
            "manual_status": "Done",
        }
        flags = detect_suspicions("Password policy", evidence)
        flag_names = [f["flag"] for f in flags]
        assert "MANUAL_WITHOUT_API" in flag_names

    def test_api_only_no_support(self):
        """API=True but no screenshot/doc/reviewer → flagged."""
        evidence = {
            "api_response": True,
            "manual_status": "Done",
        }
        flags = detect_suspicions("KYC check", evidence)
        flag_names = [f["flag"] for f in flags]
        assert "API_ONLY_NO_SUPPORT" in flag_names

    def test_screenshot_only(self):
        """Only a screenshot with no API or reviewer → suspicious."""
        evidence = {
            "screenshot_uploaded": True,
        }
        flags = detect_suspicions("AML review", evidence)
        flag_names = [f["flag"] for f in flags]
        assert "SCREENSHOT_ONLY" in flag_names

    def test_api_negative_flagged(self):
        """API explicitly returning False → flagged."""
        evidence = {
            "api_response": False,
        }
        flags = detect_suspicions("Firewall check", evidence)
        flag_names = [f["flag"] for f in flags]
        assert "API_NEGATIVE" in flag_names

    def test_mostly_empty_fields(self):
        """More than 50% null fields → MOSTLY_EMPTY flag."""
        evidence = {
            "field_1": None,
            "field_2": None,
            "field_3": "value",
        }
        flags = detect_suspicions("Test task", evidence)
        flag_names = [f["flag"] for f in flags]
        assert "MOSTLY_EMPTY" in flag_names

    def test_none_evidence_triggers_no_evidence(self):
        """None as evidence (not just empty dict) → NO_EVIDENCE."""
        flags = detect_suspicions("Test task", None)
        flag_names = [f["flag"] for f in flags]
        assert "NO_EVIDENCE" in flag_names


# -------------------------------------------------------
# Risk Score Tests
# -------------------------------------------------------

class TestRiskScore:
    """Tests for calculate_risk_score()."""

    def test_no_suspicions_zero_risk(self):
        """No suspicions → risk score should be 0."""
        assert calculate_risk_score([]) == 0

    def test_single_suspicion_adds_weight(self):
        """One suspicion should add its weight to the score."""
        suspicions = [{"flag": "TEST", "detail": "...", "weight": 20}]
        assert calculate_risk_score(suspicions) == 20

    def test_multiple_suspicions_sum(self):
        """Multiple suspicions should sum their weights."""
        suspicions = [
            {"flag": "A", "detail": "...", "weight": 25},
            {"flag": "B", "detail": "...", "weight": 30},
        ]
        assert calculate_risk_score(suspicions) == 55

    def test_capped_at_100(self):
        """Risk score should never exceed 100."""
        suspicions = [
            {"flag": "A", "detail": "...", "weight": 60},
            {"flag": "B", "detail": "...", "weight": 60},
        ]
        assert calculate_risk_score(suspicions) == 100


# -------------------------------------------------------
# Confidence Score Tests
# -------------------------------------------------------

class TestConfidenceScore:
    """Tests for calculate_confidence()."""

    def test_no_evidence_low_confidence(self):
        """Empty evidence → very low confidence."""
        score = calculate_confidence({}, [])
        assert score <= 15

    def test_full_evidence_high_confidence(self):
        """Lots of filled fields + API true → high confidence."""
        evidence = {
            "api_response": True,
            "manual_status": "Done",
            "screenshot_uploaded": True,
            "reviewer": "Amit",
        }
        score = calculate_confidence(evidence, [])
        assert score >= 80

    def test_suspicions_reduce_confidence(self):
        """Suspicion flags should reduce confidence."""
        evidence = {"api_response": True, "manual_status": "Done"}
        no_flags = calculate_confidence(evidence, [])

        flags = [
            {"flag": "A", "detail": "...", "weight": 20},
            {"flag": "B", "detail": "...", "weight": 25},
        ]
        with_flags = calculate_confidence(evidence, flags)

        assert with_flags < no_flags

    def test_confidence_never_below_5(self):
        """Confidence should always be at least 5."""
        many_flags = [{"flag": f"F{i}", "detail": "...", "weight": 30} for i in range(10)]
        score = calculate_confidence({"x": "y"}, many_flags)
        assert score >= 5


# -------------------------------------------------------
# Deterministic Verdict Tests
# -------------------------------------------------------

class TestDeterministicVerdict:
    """Tests for deterministic_verdict() — the LLM fallback."""

    def test_high_risk_non_compliant(self):
        """Risk >= 50 → NON_COMPLIANT."""
        suspicions = [{"flag": "A", "detail": "Bad stuff", "weight": 30}]
        result = deterministic_verdict("task", {"x": "y"}, suspicions, risk_score=55)
        assert result["status"] == NON_COMPLIANT

    def test_medium_risk_needs_review(self):
        """Risk 20-49 → NEEDS_REVIEW."""
        suspicions = [{"flag": "A", "detail": "Concern", "weight": 20}]
        result = deterministic_verdict("task", {"x": "y"}, suspicions, risk_score=25)
        assert result["status"] == NEEDS_REVIEW

    def test_low_risk_with_api_verified(self):
        """Risk < 20 + API=True → VERIFIED."""
        result = deterministic_verdict(
            "task", {"api_response": True}, [], risk_score=0
        )
        assert result["status"] == VERIFIED

    def test_no_api_needs_review(self):
        """Low risk but no API → NEEDS_REVIEW (can't confirm)."""
        result = deterministic_verdict(
            "task", {"manual_status": "Done"}, [], risk_score=5
        )
        assert result["status"] == NEEDS_REVIEW

    def test_result_has_required_keys(self):
        """Result dict should always have status, reason, concerns, recommendation."""
        result = deterministic_verdict("task", {}, [], risk_score=0)
        assert "status" in result
        assert "reason" in result
        assert "concerns" in result
        assert "recommendation" in result
