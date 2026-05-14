# -------------------------------------------------------
# tests/test_watchdog.py
# -------------------------------------------------------
# Unit tests for the watchdog alert system.
# -------------------------------------------------------

import pytest
from validator.watchdog import evaluate_alert, get_alert_summary


class TestEvaluateAlert:
    """Tests for the watchdog alert evaluator."""

    def test_clean_result_no_alert(self):
        result = {"risk_score": 0, "suspicion_flags": [], "status": "VERIFIED"}
        alert = evaluate_alert(result)
        assert alert["watchdog_alert"] is False
        assert alert["alert_level"] == "CLEAR"

    def test_critical_risk_triggers_critical(self):
        result = {"risk_score": 75, "suspicion_flags": ["API_NEGATIVE"], "status": "NON_COMPLIANT"}
        alert = evaluate_alert(result)
        assert alert["watchdog_alert"] is True
        assert alert["alert_level"] == "CRITICAL"
        assert alert["escalation_required"] is True

    def test_contradiction_triggers_critical(self):
        result = {"risk_score": 25, "suspicion_flags": ["CONTRADICTORY_EVIDENCE"], "status": "NEEDS_REVIEW"}
        alert = evaluate_alert(result)
        assert alert["alert_level"] == "CRITICAL"

    def test_medium_risk_triggers_warning(self):
        result = {"risk_score": 45, "suspicion_flags": ["MOSTLY_EMPTY"], "status": "NEEDS_REVIEW"}
        alert = evaluate_alert(result)
        assert alert["alert_level"] == "WARNING"
        assert alert["escalation_required"] is False

    def test_multiple_flags_triggers_warning(self):
        result = {"risk_score": 15, "suspicion_flags": ["FLAG_A", "FLAG_B"], "status": "NEEDS_REVIEW"}
        alert = evaluate_alert(result)
        assert alert["alert_level"] == "WARNING"

    def test_single_minor_flag_info(self):
        result = {"risk_score": 10, "suspicion_flags": ["SOME_FLAG"], "status": "VERIFIED"}
        alert = evaluate_alert(result)
        assert alert["alert_level"] == "INFO"

    def test_alert_has_required_keys(self):
        result = {"risk_score": 80, "suspicion_flags": [], "status": "NON_COMPLIANT"}
        alert = evaluate_alert(result)
        assert "watchdog_alert" in alert
        assert "alert_level" in alert
        assert "alert_reason" in alert
        assert "recommended_action" in alert
        assert "escalation_required" in alert
        assert "alert_timestamp" in alert


class TestAlertSummary:
    """Tests for the alert summary / health status."""

    def test_summary_has_status(self):
        summary = get_alert_summary()
        assert "status" in summary
        assert summary["status"] in ("green", "yellow", "red")

    def test_summary_has_counts(self):
        summary = get_alert_summary()
        assert "critical_count" in summary
        assert "warning_count" in summary
        assert "total_alerts" in summary
