# -------------------------------------------------------
# main.py
# -------------------------------------------------------
# Entry point for the Auto-Auditor Validator Agent.
#
# This file:
#   1. Creates the FastAPI application
#   2. Loads mock compliance-task data from a JSON file
#   3. Exposes REST endpoints so users (or other agents)
#      can list tasks and trigger validation checks.
#
# Run the server with:
#   uvicorn main:app --reload
# -------------------------------------------------------

import json
import pathlib
from fastapi import FastAPI, HTTPException

# Our own modules (from the `validator/` package)
from validator.schemas import ComplianceTask, ValidationResult
from validator.engine import validate_task

# -------------------------------------------------------
# 1.  Create the FastAPI app
# -------------------------------------------------------
app = FastAPI(
    title="Auto-Auditor Validator Agent",
    description=(
        "An Agentic AI micro-service that independently verifies "
        "whether banking compliance tasks were actually completed — "
        "instead of trusting manual status updates."
    ),
    version="1.0.0",
)

# -------------------------------------------------------
# 2.  Load mock data once at startup
# -------------------------------------------------------
# pathlib makes file paths work on Windows, Mac, and Linux
DATA_FILE = pathlib.Path(__file__).parent / "data" / "compliance_tasks.json"

def _load_tasks() -> list[ComplianceTask]:
    """
    Read the JSON file and convert each dict into a
    ComplianceTask Pydantic model.
    """
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [ComplianceTask(**item) for item in raw]


# Load once so every request reuses the same list
TASKS: list[ComplianceTask] = _load_tasks()

# -------------------------------------------------------
# 3.  API Endpoints
# -------------------------------------------------------

# --- Health check ---
@app.get("/", tags=["General"])
def health_check():
    """
    Simple health-check endpoint.
    Returns a welcome message confirming the server is up.
    """
    return {
        "message": "Auto-Auditor Validator Agent is running 🚀",
        "docs": "Visit /docs for the interactive API documentation",
    }


# --- List all tasks ---
@app.get("/tasks", response_model=list[ComplianceTask], tags=["Tasks"])
def list_tasks():
    """
    Return every compliance task from the mock database.
    """
    return TASKS


# --- Get a single task by ID ---
@app.get("/tasks/{task_id}", response_model=ComplianceTask, tags=["Tasks"])
def get_task(task_id: str):
    """
    Look up a single compliance task by its task_id.
    Returns 404 if not found.
    """
    for task in TASKS:
        if task.task_id == task_id:
            return task
    # If we reach here, the ID didn't match any task
    raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")


# --- Validate ALL tasks at once ---
# ⚠️ IMPORTANT: This route MUST come before /validate/{task_id}
# because FastAPI matches routes top-to-bottom. If the dynamic
# route came first, "all" would be treated as a task_id.
@app.get("/validate/all", response_model=list[ValidationResult], tags=["Validation"])
def validate_all():
    """
    Bulk-validate every compliance task and return
    a list of verdicts. This is the "audit report" endpoint.
    """
    return [validate_task(task) for task in TASKS]


# --- Validate a single task ---
@app.get("/validate/{task_id}", response_model=ValidationResult, tags=["Validation"])
def validate_single(task_id: str):
    """
    Run the Auto-Auditor engine on one task and return
    a PASS / FAIL / NEEDS_REVIEW verdict.
    """
    # First, find the task
    task = None
    for t in TASKS:
        if t.task_id == task_id:
            task = t
            break

    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")

    # Run the validator
    return validate_task(task)


# -------------------------------------------------------
# 4.  Mock Banking Compliance APIs
# -------------------------------------------------------
# WHY MOCK APIs?
# ──────────────
# In a real bank, the Auto-Auditor agent would call
# internal services to *independently* verify whether a
# compliance control is actually in place — rather than
# trusting a human's self-reported status.
#
# These lightweight mock endpoints simulate those internal
# services so we can develop and test the agent locally
# without needing access to production infrastructure.
#
# In production you would swap each mock with a real
# integration:
#   • /mfa-status       → bank's Identity Provider API
#                         (e.g., Okta, Azure AD, Ping)
#   • /firewall-status  → network security appliance API
#                         (e.g., Palo Alto, Fortinet)
#   • /password-policy  → Active Directory / IAM policy
#                         service (e.g., LDAP query, AWS IAM)
# -------------------------------------------------------


@app.get("/mfa-status", tags=["Mock Compliance APIs"])
def get_mfa_status():
    """
    Simulate querying the bank's Identity Provider to check
    whether Multi-Factor Authentication (MFA) is enabled
    organisation-wide.

    In production this would call an API like:
        GET https://idp.internal.bank/api/v1/mfa/status

    The mock returns MFA as *enabled* (True) — meaning this
    compliance control is currently satisfied.
    """
    return {
        "mfa_enabled": True,
    }


@app.get("/firewall-status", tags=["Mock Compliance APIs"])
def get_firewall_status():
    """
    Simulate querying the bank's network-security appliance
    to verify whether the perimeter firewall is active.

    In production this would call an API like:
        GET https://firewall.internal.bank/api/v1/status

    The mock deliberately returns *inactive* (False) so that
    the Auto-Auditor can detect and flag the non-compliance.
    This lets us test the FAIL / NEEDS_REVIEW logic paths.
    """
    return {
        "firewall_active": False,
    }


@app.get("/password-policy", tags=["Mock Compliance APIs"])
def get_password_policy():
    """
    Simulate querying the bank's IAM / Active Directory
    service to retrieve the current password-policy settings.

    In production this would call an API like:
        GET https://iam.internal.bank/api/v1/password-policy

    The mock returns a policy that requires:
      • A minimum password length of 12 characters
      • At least one special character
    These values mirror typical banking-industry standards
    (e.g., NIST SP 800-63B recommendations).
    """
    return {
        "minimum_length": 12,
        "special_characters_required": True,
    }


# -------------------------------------------------------
# 5.  Validator Agent — Full Audit Endpoint
# -------------------------------------------------------
# This endpoint triggers the Validator Agent to call all
# mock compliance APIs over HTTP, evaluate each control,
# and return a consolidated audit report.
#
# The agent lives in `validator/agent.py` and uses the
# `requests` library to call the /mfa-status,
# /firewall-status, and /password-policy endpoints above.
#
# Usage:
#   GET /audit   →  returns the full compliance report
# -------------------------------------------------------

from validator.agent import run_all_checks


@app.get("/audit", tags=["Validator Agent"])
def run_audit():
    """
    Trigger the Auto-Auditor Validator Agent to perform a
    full compliance audit.

    The agent independently calls each mock compliance API,
    evaluates the response against banking regulations, and
    returns a consolidated report with verdicts:

    - **VERIFIED** — the control meets compliance rules
    - **NON-COMPLIANT** — the control fails compliance rules
    - **NEEDS MANUAL REVIEW** — API unreachable or data ambiguous
    """
    return run_all_checks()


# -------------------------------------------------------
# 6.  Smart Audit — AI-Powered (ML + LLM)
# -------------------------------------------------------
# This endpoint combines three layers of intelligence:
#   1. Rule-based compliance checks (deterministic)
#   2. Custom-trained ML model (risk classification)
#   3. Local LLM via Ollama (natural language reasoning)
#
# The system degrades gracefully:
#   - Full mode:  ML + Ollama both available
#   - ML-only:    Ollama not running, template reasoning
#   - LLM-only:   Model not trained, LLM reasons directly
#   - Basic:      Neither available, rule-based only
#
# Usage:
#   GET /audit/smart   →  returns the comprehensive report
# -------------------------------------------------------

from validator.agent import run_smart_audit


@app.get("/audit/smart", tags=["Smart Audit (AI-Powered)"])
def run_smart_audit_endpoint():
    """
    Trigger a comprehensive AI-powered compliance audit.

    This is the **flagship endpoint** — it combines:

    - **Rule-based checks** for deterministic compliance verdicts
    - **Custom ML model** (Random Forest) for risk level and score
    - **Local LLM** (Ollama) for natural-language audit reasoning

    The response includes:
    - Infrastructure check results
    - Task validation results
    - ML risk prediction (risk level, compliance score, feature importances)
    - AI-generated audit report (executive summary, findings, remediation plan)

    **Note:** The response will indicate which AI mode is active
    (full/ml-only/llm-only/basic) depending on what's available.
    """
    return run_smart_audit()


# -------------------------------------------------------
# 7.  Reasoning Validator — Intelligent LLM-Powered
# -------------------------------------------------------
# This is the FLAGSHIP endpoint of the Auto-Auditor.
#
# It accepts any compliance task + evidence via POST,
# runs hybrid deterministic + LLM reasoning, and returns
# a standardised verdict with confidence and risk scores.
#
# Integration-ready for:
#   • Dispatcher Agent  → sends tasks here for validation
#   • Spectre-Sentinel  → consumes risk scores for alerting
#   • Frontend Dashboard → displays verdicts in real-time
#
# Usage:
#   POST /reasoning-validate
#   Body: {"task_id": 1, "task": "...", "evidence": {...}}
# -------------------------------------------------------

from validator.reasoning_engine import reason_and_validate
from validator.audit_logger import log_validation, get_audit_trail, get_audit_stats
from validator.schemas import ReasoningRequest, ReasoningResponse


@app.post(
    "/reasoning-validate",
    response_model=ReasoningResponse,
    tags=["Reasoning Validator (AI-Powered)"],
)
def reasoning_validate(request: ReasoningRequest):
    """
    **Intelligent Compliance Validation** — the core agentic endpoint.

    Accepts a compliance task and its evidence, then runs a
    **hybrid reasoning pipeline**:

    1. **Deterministic suspicion detection** — catches contradictions,
       missing data, and fabrication patterns instantly
    2. **LLM reasoning** (Ollama/phi3) — analyses the evidence like
       a human auditor and provides nuanced judgment
    3. **Risk & confidence scoring** — quantifies how suspicious
       the evidence is and how confident the verdict is

    **Input example:**
    ```json
    {
        "task_id": 1,
        "task": "Enable MFA for admin accounts",
        "evidence": {
            "api_response": true,
            "manual_status": "Done",
            "screenshot_uploaded": true
        }
    }
    ```

    **Output:**
    - `status`: VERIFIED / NON_COMPLIANT / NEEDS_REVIEW
    - `confidence_score`: 0-100
    - `risk_score`: 0-100
    - `reason`: human-readable explanation
    - `suspicion_flags`: what the rules caught
    - `llm_used`: whether the LLM was involved

    **Falls back gracefully** to deterministic-only reasoning
    if Ollama is not running.
    """

    # Run the reasoning engine
    result = reason_and_validate(
        task_id=request.task_id,
        task=request.task,
        evidence=request.evidence,
    )

    # Add the task description to the result for audit logging
    result["task"] = request.task

    # Log to the audit trail
    log_validation(result)

    return result


# -------------------------------------------------------
# 8.  Audit Trail Endpoints
# -------------------------------------------------------
# These endpoints expose the audit log for monitoring
# and compliance reporting purposes.
# -------------------------------------------------------

@app.get("/audit-trail", tags=["Audit Trail"])
def view_audit_trail(limit: int = 50):
    """
    View the most recent validation audit log entries.

    Returns entries newest-first, with a configurable limit.
    Each entry records: task, timestamp, verdict, risk score,
    and which reasoning method was used.

    Use this for compliance reporting and pattern analysis.
    """
    return {
        "entries": get_audit_trail(limit=limit),
        "total_returned": min(limit, len(get_audit_trail(limit=limit))),
    }


@app.get("/audit-stats", tags=["Audit Trail"])
def view_audit_stats():
    """
    Get summary statistics from the audit trail.

    Returns:
    - Total validations performed
    - Breakdown by verdict (VERIFIED / NON_COMPLIANT / NEEDS_REVIEW)
    - Average risk score
    - Number of high-risk validations

    Useful for the Spectre-Sentinel Watchdog and dashboards.
    """
    return get_audit_stats()


# -------------------------------------------------------
# 9.  Watchdog Endpoints (Spectre-Sentinel Integration)
# -------------------------------------------------------
# These endpoints are designed for the Spectre-Sentinel
# Watchdog system to consume. It can poll these to detect
# suspicious compliance activity in near-real-time.
# -------------------------------------------------------

from validator.watchdog import get_recent_alerts, get_alert_summary


@app.get("/watchdog/alerts", tags=["Watchdog (Spectre-Sentinel)"])
def watchdog_alerts(limit: int = 20):
    """
    Get recent watchdog alerts for Spectre-Sentinel.

    Returns alerts generated when suspicious compliance
    activity is detected. Alerts include:
    - **CRITICAL** — immediate human intervention needed
    - **WARNING** — investigate within 24 hours
    - **INFO** — minor concern, monitor

    Poll this endpoint to monitor compliance health.
    """
    alerts = get_recent_alerts(limit=limit)
    return {
        "alerts": alerts,
        "total": len(alerts),
    }


@app.get("/watchdog/status", tags=["Watchdog (Spectre-Sentinel)"])
def watchdog_status():
    """
    Get the overall compliance health status.

    Returns a traffic-light status for quick monitoring:
    - 🟢 **green** — no alerts, all clear
    - 🟡 **yellow** — warnings detected, investigation needed
    - 🔴 **red** — critical alerts, immediate action required

    Spectre-Sentinel uses this for its health dashboard.
    """
    return get_alert_summary()

