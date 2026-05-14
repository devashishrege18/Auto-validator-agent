# -------------------------------------------------------
# validator/audit_logger.py
# -------------------------------------------------------
# Lightweight audit trail logger.
#
# Every validation result is appended to a JSON-lines file
# (one JSON object per line) so we have a complete,
# tamper-evident audit trail.
#
# This is intentionally simple — in production you'd
# send these to a proper audit database (e.g., PostgreSQL
# with append-only tables, or a blockchain ledger).
#
# Architecture-ready: The Spectre-Sentinel Watchdog can
# tail this file to monitor for suspicious patterns.
# -------------------------------------------------------

import json
import pathlib
from datetime import datetime, timezone
from typing import Any

# -------------------------------------------------------
# Configuration
# -------------------------------------------------------
# Audit log lives in the data/ directory alongside other
# project data files.
LOG_DIR = pathlib.Path(__file__).parent.parent / "data"
AUDIT_LOG_FILE = LOG_DIR / "audit_log.jsonl"


# -------------------------------------------------------
# Log a Validation Result
# -------------------------------------------------------

def log_validation(result: dict[str, Any]) -> dict[str, Any]:
    """
    Append a validation result to the audit trail.

    Parameters
    ----------
    result : dict
        The validation result from the reasoning engine.
        Must contain at minimum: task_id, status, risk_score.

    Returns
    -------
    dict
        The audit log entry that was written (includes
        a log_id and log_timestamp for traceability).
    """

    # Build the audit log entry
    log_entry = {
        "log_id": _generate_log_id(),
        "log_timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": result.get("task_id"),
        "task": result.get("task", ""),
        "status": result.get("status"),
        "confidence_score": result.get("confidence_score"),
        "risk_score": result.get("risk_score"),
        "reason": result.get("reason"),
        "suspicion_flags": result.get("suspicion_flags", []),
        "severity": result.get("severity", "MEDIUM"),
        "task_category": result.get("task_category", "default"),
        "evidence_quality": result.get("evidence_quality", "unknown"),
        "watchdog_alert": result.get("watchdog_alert", False),
        "alert_level": result.get("alert_level", "CLEAR"),
        "llm_used": result.get("llm_used", False),
    }

    # Ensure the data directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Append to the JSONL file (one JSON object per line)
    # Using 'a' mode = append, so existing entries are preserved
    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        print(f"[AUDIT] Logged validation for task {result.get('task_id')}")
    except Exception as e:
        print(f"[AUDIT] Failed to write log: {e}")

    return log_entry


# -------------------------------------------------------
# Read Audit Trail
# -------------------------------------------------------

def get_audit_trail(limit: int = 50) -> list[dict]:
    """
    Read the most recent audit log entries.

    Parameters
    ----------
    limit : int
        Maximum number of entries to return (most recent first).

    Returns
    -------
    list[dict]
        List of audit log entries, newest first.
    """
    if not AUDIT_LOG_FILE.exists():
        return []

    entries = []
    try:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue  # Skip malformed lines
    except Exception as e:
        print(f"[AUDIT] Failed to read log: {e}")
        return []

    # Return most recent entries first
    entries.reverse()
    return entries[:limit]


# -------------------------------------------------------
# Audit Statistics
# -------------------------------------------------------

def get_audit_stats() -> dict:
    """
    Get summary statistics from the audit trail.

    Returns
    -------
    dict with:
        total_validations — how many validations have been run
        status_counts     — breakdown by verdict
        avg_risk_score    — average risk score across all validations
        high_risk_count   — number of validations with risk >= 50
    """
    entries = get_audit_trail(limit=10000)

    if not entries:
        return {
            "total_validations": 0,
            "status_counts": {},
            "avg_risk_score": 0,
            "high_risk_count": 0,
        }

    status_counts = {}
    total_risk = 0
    high_risk = 0

    for entry in entries:
        # Count statuses
        status = entry.get("status", "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1

        # Risk scores
        risk = entry.get("risk_score", 0) or 0
        total_risk += risk
        if risk >= 50:
            high_risk += 1

    return {
        "total_validations": len(entries),
        "status_counts": status_counts,
        "avg_risk_score": round(total_risk / len(entries), 1),
        "high_risk_count": high_risk,
    }


# -------------------------------------------------------
# Helper
# -------------------------------------------------------

_log_counter = 0

def _generate_log_id() -> str:
    """Generate a simple sequential log ID."""
    global _log_counter
    _log_counter += 1
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"LOG-{ts}-{_log_counter:04d}"
