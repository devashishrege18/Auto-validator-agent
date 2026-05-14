# -------------------------------------------------------
# validator/watchdog.py
# -------------------------------------------------------
# Watchdog Alert System for Spectre-Sentinel Integration.
#
# This module evaluates validation results and generates
# structured alert signals that a monitoring system
# (Spectre-Sentinel Watchdog) can consume to trigger
# escalation workflows.
#
# Alert Levels:
#   CRITICAL — immediate human intervention required
#   WARNING  — suspicious activity, investigate soon
#   INFO     — minor concern, monitor
#   CLEAR    — no issues detected
#
# Integration:
#   Spectre-Sentinel polls GET /watchdog/alerts and
#   GET /watchdog/status to monitor compliance posture.
# -------------------------------------------------------

from datetime import datetime, timezone
from typing import Any

# -------------------------------------------------------
# In-memory alert buffer
# -------------------------------------------------------
# Recent alerts are kept in memory for quick access.
# In production, these would go to a message queue
# (e.g., Redis, RabbitMQ) or a database.
# -------------------------------------------------------
_alert_buffer: list[dict] = []
MAX_BUFFER_SIZE = 200


# -------------------------------------------------------
# Alert Level Thresholds
# -------------------------------------------------------
CRITICAL_RISK_THRESHOLD = 70
WARNING_RISK_THRESHOLD = 40
CRITICAL_FLAG_PATTERNS = [
    "CONTRADICTORY_EVIDENCE",
    "NO_EVIDENCE",
    "API_UNAVAILABLE_BYPASS",
]
WARNING_FLAG_PATTERNS = [
    "MANUAL_WITHOUT_API",
    "SCREENSHOT_ONLY",
    "TIMESTAMP_ANOMALY",
    "SUSPICIOUSLY_FAST",
]


# -------------------------------------------------------
# Main Alert Evaluator
# -------------------------------------------------------

def evaluate_alert(result: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluate a validation result and generate a watchdog
    alert if suspicious activity is detected.

    Parameters
    ----------
    result : dict
        A validation result from the reasoning engine.
        Expected keys: status, risk_score, confidence_score,
        suspicion_flags, reason.

    Returns
    -------
    dict with:
        watchdog_alert     — True if alert triggered
        alert_level        — CRITICAL | WARNING | INFO | CLEAR
        alert_reason       — why the alert was triggered
        recommended_action — what should happen next
        escalation_required — whether a human must act now
        alert_timestamp    — when the alert was generated
    """

    risk_score = result.get("risk_score", 0)
    flags = result.get("suspicion_flags", [])
    status = result.get("status", "")
    confidence = result.get("confidence_score", 50)

    # --------------------------------------------------
    # Rule 1: CRITICAL — high risk or critical flags
    # --------------------------------------------------
    has_critical_flag = any(f in CRITICAL_FLAG_PATTERNS for f in flags)

    if risk_score >= CRITICAL_RISK_THRESHOLD or has_critical_flag:
        alert = _build_alert(
            level="CRITICAL",
            reason=_build_critical_reason(risk_score, flags, status),
            action=(
                "Immediately escalate to senior compliance officer. "
                "Suspend the task until manual verification is complete. "
                "Preserve all evidence for forensic review."
            ),
            escalation=True,
            result=result,
        )
        _store_alert(alert)
        return alert

    # --------------------------------------------------
    # Rule 2: WARNING — medium risk or warning flags
    # --------------------------------------------------
    has_warning_flag = any(f in WARNING_FLAG_PATTERNS for f in flags)

    if (risk_score >= WARNING_RISK_THRESHOLD
            or len(flags) >= 2
            or has_warning_flag):
        alert = _build_alert(
            level="WARNING",
            reason=_build_warning_reason(risk_score, flags, confidence),
            action=(
                "Schedule manual review within 24 hours. "
                "Request additional evidence from the task owner. "
                "Flag for next compliance team standup."
            ),
            escalation=False,
            result=result,
        )
        _store_alert(alert)
        return alert

    # --------------------------------------------------
    # Rule 3: INFO — single low-weight flag
    # --------------------------------------------------
    if flags:
        alert = _build_alert(
            level="INFO",
            reason=(
                f"Minor concern detected: {', '.join(flags)}. "
                f"Risk score ({risk_score}) is within acceptable range."
            ),
            action="Monitor in next regular audit cycle. No immediate action needed.",
            escalation=False,
            result=result,
        )
        _store_alert(alert)
        return alert

    # --------------------------------------------------
    # Rule 4: CLEAR — no issues
    # --------------------------------------------------
    return _build_alert(
        level="CLEAR",
        reason="No suspicious activity detected. Evidence is consistent.",
        action="No action needed.",
        escalation=False,
        result=result,
    )


# -------------------------------------------------------
# Alert Reason Builders
# -------------------------------------------------------

def _build_critical_reason(
    risk_score: int,
    flags: list[str],
    status: str,
) -> str:
    """Build a detailed reason string for CRITICAL alerts."""
    parts = []

    if risk_score >= CRITICAL_RISK_THRESHOLD:
        parts.append(
            f"Risk score ({risk_score}/100) exceeds critical threshold."
        )

    if "CONTRADICTORY_EVIDENCE" in flags:
        parts.append(
            "CONTRADICTION: Manual status contradicts API verification. "
            "Potential manual bypass or evidence fabrication detected."
        )

    if "NO_EVIDENCE" in flags:
        parts.append(
            "No evidence provided for a completed task. "
            "This is a major compliance gap."
        )

    if "API_UNAVAILABLE_BYPASS" in flags:
        parts.append(
            "Task was marked complete while API verification was unavailable. "
            "Possible attempt to bypass automated checks."
        )

    if status == "NON_COMPLIANT":
        parts.append("System is confirmed non-compliant.")

    return " ".join(parts) if parts else "Critical risk level detected."


def _build_warning_reason(
    risk_score: int,
    flags: list[str],
    confidence: int,
) -> str:
    """Build a detailed reason string for WARNING alerts."""
    parts = []

    if risk_score >= WARNING_RISK_THRESHOLD:
        parts.append(f"Elevated risk score: {risk_score}/100.")

    if len(flags) >= 2:
        parts.append(
            f"Multiple suspicion flags triggered: {', '.join(flags)}."
        )

    if confidence < 50:
        parts.append(
            f"Low confidence ({confidence}%) in the validation verdict."
        )

    return " ".join(parts) if parts else "Suspicious patterns detected."


# -------------------------------------------------------
# Alert Builder & Storage
# -------------------------------------------------------

def _build_alert(
    level: str,
    reason: str,
    action: str,
    escalation: bool,
    result: dict,
) -> dict:
    """Build a standardised alert dictionary."""
    return {
        "watchdog_alert": level != "CLEAR",
        "alert_level": level,
        "alert_reason": reason,
        "recommended_action": action,
        "escalation_required": escalation,
        "alert_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_task_id": result.get("task_id"),
        "source_risk_score": result.get("risk_score", 0),
        "source_status": result.get("status", ""),
    }


def _store_alert(alert: dict) -> None:
    """Store an alert in the in-memory buffer."""
    global _alert_buffer
    _alert_buffer.append(alert)

    # Trim buffer if it exceeds max size
    if len(_alert_buffer) > MAX_BUFFER_SIZE:
        _alert_buffer = _alert_buffer[-MAX_BUFFER_SIZE:]


# -------------------------------------------------------
# Alert Query Functions (for API endpoints)
# -------------------------------------------------------

def get_recent_alerts(limit: int = 20) -> list[dict]:
    """
    Get the most recent watchdog alerts.

    Parameters
    ----------
    limit : int
        Maximum number of alerts to return.

    Returns
    -------
    list[dict]
        Alerts sorted newest-first.
    """
    return list(reversed(_alert_buffer[-limit:]))


def get_alert_summary() -> dict:
    """
    Get a summary of the current alert status for
    Spectre-Sentinel health monitoring.

    Returns
    -------
    dict with:
        status           — "green" | "yellow" | "red"
        total_alerts     — total alerts in buffer
        critical_count   — number of CRITICAL alerts
        warning_count    — number of WARNING alerts
        last_alert_time  — timestamp of most recent alert
    """
    critical = sum(1 for a in _alert_buffer if a["alert_level"] == "CRITICAL")
    warning = sum(1 for a in _alert_buffer if a["alert_level"] == "WARNING")

    # Determine overall status
    if critical > 0:
        status = "red"
    elif warning > 0:
        status = "yellow"
    else:
        status = "green"

    return {
        "status": status,
        "total_alerts": len(_alert_buffer),
        "critical_count": critical,
        "warning_count": warning,
        "info_count": sum(1 for a in _alert_buffer if a["alert_level"] == "INFO"),
        "last_alert_time": (
            _alert_buffer[-1]["alert_timestamp"]
            if _alert_buffer else None
        ),
    }
