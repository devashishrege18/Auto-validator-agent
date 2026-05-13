# -------------------------------------------------------
# validator/agent.py
# -------------------------------------------------------
# The Compliance Validator Agent — an autonomous checker
# that calls the bank's compliance APIs *over HTTP* and
# independently verifies whether each security control
# meets regulatory requirements.
#
# HOW IT WORKS (high-level)
# ─────────────────────────
#  1. The agent holds a registry of "compliance checks",
#     each one tied to a specific API endpoint.
#  2. For every check it:
#        a) Calls the endpoint using the `requests` lib
#        b) Extracts the relevant field from the response
#        c) Evaluates the field against a compliance rule
#        d) Returns one of three verdicts:
#             • VERIFIED          — control is in place ✅
#             • NON-COMPLIANT     — control is missing  ❌
#             • NEEDS MANUAL REVIEW — API failed or data
#               is ambiguous, a human must investigate 🔍
#  3. A convenience method `run_all_checks()` executes
#     every registered check and returns a full report.
#
# WHY USE `requests` INSTEAD OF INTERNAL FUNCTION CALLS?
# ──────────────────────────────────────────────────────
# In production the compliance APIs will live on separate
# servers (identity provider, firewall appliance, IAM
# service).  By calling them over HTTP even in dev, we:
#   • Keep the agent decoupled from the services it audits
#   • Make it trivial to swap mock URLs for real ones
#   • Exercise the same network-error-handling code paths
#     that production will need
# -------------------------------------------------------

import requests
from datetime import datetime, timezone
from typing import Any


# -------------------------------------------------------
# Configuration
# -------------------------------------------------------
# Base URL of the FastAPI server hosting the mock APIs.
# Change this when pointing at staging / production.
BASE_URL = "http://127.0.0.1:8000"

# How long (in seconds) we wait for an API response
# before giving up and returning NEEDS MANUAL REVIEW.
REQUEST_TIMEOUT = 5


# -------------------------------------------------------
# Verdict Constants
# -------------------------------------------------------
# Using named constants avoids typos and makes it easy
# to search the codebase for every place a verdict is
# used.
VERIFIED = "VERIFIED"
NON_COMPLIANT = "NON-COMPLIANT"
NEEDS_MANUAL_REVIEW = "NEEDS MANUAL REVIEW"


# -------------------------------------------------------
# Helper — safe API caller
# -------------------------------------------------------
def _call_api(endpoint: str) -> dict[str, Any] | None:
    """
    Make a GET request to a compliance API endpoint.

    Parameters
    ----------
    endpoint : str
        The path to call, e.g. "/mfa-status".

    Returns
    -------
    dict | None
        The parsed JSON response on success, or None if
        the request failed for any reason (timeout,
        connection error, non-200 status, invalid JSON).

    Why return None on failure?
    --------------------------
    Returning None (instead of raising) lets the caller
    use a simple `if response is None` check to trigger
    the NEEDS MANUAL REVIEW path, keeping the validation
    logic clean and readable.
    """
    url = f"{BASE_URL}{endpoint}"
    try:
        # --------------------------------------------------
        # Make the HTTP GET request with a timeout.
        # If the server is down or too slow, `requests`
        # raises a ConnectionError or Timeout exception
        # which we catch below.
        # --------------------------------------------------
        response = requests.get(url, timeout=REQUEST_TIMEOUT)

        # --------------------------------------------------
        # Check for HTTP errors (4xx, 5xx).
        # raise_for_status() converts a bad status code
        # into a requests.HTTPError exception.
        # --------------------------------------------------
        response.raise_for_status()

        # --------------------------------------------------
        # Parse the JSON body.  If the body isn't valid
        # JSON, .json() raises a ValueError which we
        # also catch below.
        # --------------------------------------------------
        return response.json()

    except requests.exceptions.ConnectionError:
        # Server is unreachable (not running, wrong host/port)
        print(f"[AGENT] ❌ Connection failed: {url}")
        return None

    except requests.exceptions.Timeout:
        # Server took too long to respond
        print(f"[AGENT] ⏱️  Request timed out: {url}")
        return None

    except requests.exceptions.HTTPError as exc:
        # Server returned a non-2xx status code
        print(f"[AGENT] ⚠️  HTTP error from {url}: {exc}")
        return None

    except (ValueError, requests.exceptions.JSONDecodeError):
        # Response body was not valid JSON
        print(f"[AGENT] ⚠️  Invalid JSON from {url}")
        return None


# -------------------------------------------------------
# Individual Compliance Checks
# -------------------------------------------------------
# Each function below follows the same pattern:
#   1. Call the relevant API
#   2. If the call failed → NEEDS MANUAL REVIEW
#   3. If the expected key is missing → NEEDS MANUAL REVIEW
#   4. Evaluate the value against the compliance rule
#   5. Return a structured result dict
# -------------------------------------------------------

def check_mfa() -> dict[str, str]:
    """
    COMPLIANCE RULE: Multi-Factor Authentication must be
    enabled (mfa_enabled == True).

    Regulatory basis: RBI Cybersecurity Framework, PCI-DSS
    Requirement 8.3 — MFA is mandatory for all personnel
    with access to cardholder data environments.

    Returns
    -------
    dict with keys:
        check    — name of the compliance check
        verdict  — VERIFIED | NON-COMPLIANT | NEEDS MANUAL REVIEW
        details  — human-readable explanation
    """
    # Step 1: Call the MFA status API
    data = _call_api("/mfa-status")

    # Step 2: Handle API failure — we can't verify, flag for manual review
    if data is None:
        return {
            "check": "Multi-Factor Authentication (MFA)",
            "verdict": NEEDS_MANUAL_REVIEW,
            "details": (
                "Could not reach the MFA status API. "
                "A human auditor must verify MFA status manually."
            ),
        }

    # Step 3: Check if the expected key exists in the response
    if "mfa_enabled" not in data:
        return {
            "check": "Multi-Factor Authentication (MFA)",
            "verdict": NEEDS_MANUAL_REVIEW,
            "details": (
                "The MFA API responded but did not include the "
                "'mfa_enabled' field. Data format may have changed."
            ),
        }

    # Step 4: Evaluate the compliance rule
    mfa_enabled = data["mfa_enabled"]

    if mfa_enabled is True:
        # ✅ MFA is on — compliant
        return {
            "check": "Multi-Factor Authentication (MFA)",
            "verdict": VERIFIED,
            "details": "MFA is enabled organisation-wide. Compliant.",
        }
    else:
        # ❌ MFA is off — non-compliant
        return {
            "check": "Multi-Factor Authentication (MFA)",
            "verdict": NON_COMPLIANT,
            "details": (
                "MFA is NOT enabled. This violates PCI-DSS 8.3. "
                "Immediate remediation required."
            ),
        }


def check_firewall() -> dict[str, str]:
    """
    COMPLIANCE RULE: The perimeter firewall must be active
    (firewall_active == True).

    Regulatory basis: PCI-DSS Requirement 1.1 — a firewall
    configuration must be established and maintained to
    protect cardholder data.

    Returns
    -------
    dict with keys: check, verdict, details
    """
    # Step 1: Call the firewall status API
    data = _call_api("/firewall-status")

    # Step 2: Handle API failure
    if data is None:
        return {
            "check": "Perimeter Firewall",
            "verdict": NEEDS_MANUAL_REVIEW,
            "details": (
                "Could not reach the firewall status API. "
                "A human auditor must verify firewall status manually."
            ),
        }

    # Step 3: Check for expected key
    if "firewall_active" not in data:
        return {
            "check": "Perimeter Firewall",
            "verdict": NEEDS_MANUAL_REVIEW,
            "details": (
                "The firewall API responded but did not include "
                "'firewall_active'. Data format may have changed."
            ),
        }

    # Step 4: Evaluate the compliance rule
    firewall_active = data["firewall_active"]

    if firewall_active is True:
        # ✅ Firewall is running — compliant
        return {
            "check": "Perimeter Firewall",
            "verdict": VERIFIED,
            "details": "Firewall is active and protecting the perimeter. Compliant.",
        }
    else:
        # ❌ Firewall is down — critical non-compliance
        return {
            "check": "Perimeter Firewall",
            "verdict": NON_COMPLIANT,
            "details": (
                "Firewall is INACTIVE. This is a critical PCI-DSS 1.1 "
                "violation. The network perimeter is unprotected."
            ),
        }


def check_password_policy() -> dict[str, str]:
    """
    COMPLIANCE RULE: Password policy must enforce a
    minimum length of at least 12 characters.

    Regulatory basis: NIST SP 800-63B and RBI guidelines
    recommend a minimum of 12 characters for privileged
    accounts in banking environments.

    Returns
    -------
    dict with keys: check, verdict, details
    """
    # Step 1: Call the password policy API
    data = _call_api("/password-policy")

    # Step 2: Handle API failure
    if data is None:
        return {
            "check": "Password Policy",
            "verdict": NEEDS_MANUAL_REVIEW,
            "details": (
                "Could not reach the password policy API. "
                "A human auditor must verify password policy manually."
            ),
        }

    # Step 3: Check for expected key
    if "minimum_length" not in data:
        return {
            "check": "Password Policy",
            "verdict": NEEDS_MANUAL_REVIEW,
            "details": (
                "The password policy API responded but did not "
                "include 'minimum_length'. Data format may have changed."
            ),
        }

    # Step 4: Evaluate the compliance rule
    min_length = data["minimum_length"]

    # Extra safety: make sure the value is actually a number
    if not isinstance(min_length, (int, float)):
        return {
            "check": "Password Policy",
            "verdict": NEEDS_MANUAL_REVIEW,
            "details": (
                f"'minimum_length' is '{min_length}' (not a number). "
                "Cannot evaluate compliance — manual review needed."
            ),
        }

    if min_length >= 12:
        # ✅ Meets the minimum — compliant
        return {
            "check": "Password Policy",
            "verdict": VERIFIED,
            "details": (
                f"Password minimum length is {min_length} characters "
                f"(≥ 12 required). Compliant."
            ),
        }
    else:
        # ❌ Too short — non-compliant
        return {
            "check": "Password Policy",
            "verdict": NON_COMPLIANT,
            "details": (
                f"Password minimum length is only {min_length} characters. "
                f"Must be at least 12 per NIST SP 800-63B."
            ),
        }


# -------------------------------------------------------
# Full Audit Run
# -------------------------------------------------------

def run_all_checks() -> dict[str, Any]:
    """
    Execute every compliance check and compile a full
    audit report.

    Returns
    -------
    dict with keys:
        timestamp    — when the audit was performed (UTC)
        summary      — quick counts of each verdict type
        checks       — list of individual check results
        overall      — overall compliance status:
                       "FULLY COMPLIANT" only if every
                       check is VERIFIED; otherwise
                       "ACTION REQUIRED"

    This is the main entry point an auditor (or an
    automated scheduler) would call to get a complete
    picture of the bank's compliance posture.
    """
    # --------------------------------------------------
    # 1. Run all individual checks
    # --------------------------------------------------
    # To add a new compliance check in the future, simply
    # write a new check_xxx() function and append it here.
    results = [
        check_mfa(),
        check_firewall(),
        check_password_policy(),
    ]

    # --------------------------------------------------
    # 2. Count verdicts for the summary
    # --------------------------------------------------
    verdict_counts = {
        VERIFIED: 0,
        NON_COMPLIANT: 0,
        NEEDS_MANUAL_REVIEW: 0,
    }
    for result in results:
        verdict_counts[result["verdict"]] += 1

    # --------------------------------------------------
    # 3. Determine overall compliance status
    # --------------------------------------------------
    # The bank is only "FULLY COMPLIANT" when every single
    # check comes back VERIFIED. Even one NON-COMPLIANT
    # or NEEDS MANUAL REVIEW means action is required.
    if verdict_counts[VERIFIED] == len(results):
        overall = "FULLY COMPLIANT"
    else:
        overall = "ACTION REQUIRED"

    # --------------------------------------------------
    # 4. Compile and return the audit report
    # --------------------------------------------------
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "summary": {
            "total_checks": len(results),
            "verified": verdict_counts[VERIFIED],
            "non_compliant": verdict_counts[NON_COMPLIANT],
            "needs_manual_review": verdict_counts[NEEDS_MANUAL_REVIEW],
        },
        "checks": results,
    }


# -------------------------------------------------------
# Smart Audit — ML + LLM Powered
# -------------------------------------------------------
# This function combines all three layers:
#   1. Rule-based checks (infrastructure compliance)
#   2. ML model predictions (risk level + score)
#   3. LLM reasoning (natural language analysis)
#
# It calls the existing task validation engine as well,
# giving a complete picture of the bank's compliance.
# -------------------------------------------------------

from validator import ml_model
from validator import llm_reasoner


def _get_task_results() -> list[dict]:
    """
    Call the task validation endpoint internally to get
    task-level compliance results.

    Instead of making an HTTP call to ourselves, we
    import the engine directly for speed and reliability.
    """
    from validator.engine import validate_task
    from validator.schemas import ComplianceTask
    import json
    import pathlib

    data_file = pathlib.Path(__file__).parent.parent / "data" / "compliance_tasks.json"
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            raw = json.load(f)
        tasks = [ComplianceTask(**item) for item in raw]
        # Convert ValidationResult objects to dicts
        return [validate_task(t).model_dump() for t in tasks]
    except Exception as exc:
        print(f"[AGENT] Could not load task data: {exc}")
        return []


def run_smart_audit() -> dict[str, Any]:
    """
    Execute a comprehensive AI-powered compliance audit.

    This is the flagship feature of the Auto-Auditor —
    combining three layers of intelligence:

    Layer 1: Rule-Based Checks
        Deterministic infrastructure compliance checks
        (MFA, firewall, password policy).

    Layer 2: ML Risk Classification
        A custom-trained Random Forest model that predicts
        the overall risk level (LOW/MEDIUM/HIGH/CRITICAL)
        and compliance score (0-100).

    Layer 3: LLM Audit Reasoning
        A local LLM (via Ollama) that analyses all results
        and writes a professional audit report with findings,
        risk assessment, and remediation recommendations.

    Returns
    -------
    dict with keys:
        timestamp           — when the audit was performed
        overall             — overall status from rule checks
        mode                — which AI layers are active
        infrastructure      — rule-based check results
        task_validation     — task-level validation results
        ml_prediction       — ML risk prediction (or null)
        ai_reasoning        — LLM/template audit report
        summary             — quick verdict counts
    """

    # --------------------------------------------------
    # Layer 1: Rule-Based Infrastructure Checks
    # --------------------------------------------------
    rule_report = run_all_checks()
    infrastructure_checks = rule_report["checks"]

    # --------------------------------------------------
    # Layer 2: Task Validation
    # --------------------------------------------------
    task_results = _get_task_results()

    # --------------------------------------------------
    # Layer 3: ML Risk Prediction
    # --------------------------------------------------
    ml_prediction = ml_model.predict(infrastructure_checks, task_results)

    # Determine which AI layers are active
    has_ml = ml_prediction is not None
    has_llm = llm_reasoner.is_ollama_available()

    if has_ml and has_llm:
        mode = "full (ML + LLM)"
    elif has_ml:
        mode = "ml-only (template reasoning)"
    elif has_llm:
        mode = "llm-only (no ML model)"
    else:
        mode = "basic (rule-based only)"

    # --------------------------------------------------
    # Layer 4: LLM / Template Reasoning
    # --------------------------------------------------
    reasoning = llm_reasoner.generate_reasoning(
        infrastructure_checks, task_results, ml_prediction
    )

    # --------------------------------------------------
    # Compile the full report
    # --------------------------------------------------
    return {
        "timestamp": rule_report["timestamp"],
        "overall": rule_report["overall"],
        "mode": mode,
        "infrastructure_checks": infrastructure_checks,
        "task_validation": task_results,
        "ml_prediction": ml_prediction,
        "ai_reasoning": reasoning,
        "summary": {
            **rule_report["summary"],
            "tasks_total": len(task_results),
            "tasks_passed": sum(
                1 for t in task_results if t.get("verdict") == "PASS"
            ),
            "tasks_failed": sum(
                1 for t in task_results if t.get("verdict") == "FAIL"
            ),
            "tasks_needs_review": sum(
                1 for t in task_results
                if t.get("verdict") == "NEEDS_REVIEW"
            ),
        },
    }


# -------------------------------------------------------
# CLI Entry Point
# -------------------------------------------------------
# This allows running the agent directly from the
# terminal for quick testing:
#
#   python -m validator.agent
#
# Make sure the FastAPI server is running first:
#   uvicorn main:app --reload
# -------------------------------------------------------

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("  AUTO-AUDITOR VALIDATOR AGENT - Compliance Report")
    print("=" * 60)
    print()

    report = run_all_checks()

    # Pretty-print the full JSON report
    print(json.dumps(report, indent=2, ensure_ascii=True))

    print()
    print("=" * 60)
    print(f"  OVERALL STATUS: {report['overall']}")
    print("=" * 60)

    # Also print a human-friendly summary table
    print()
    print(f"  {'Check':<40} {'Verdict':<22}")
    print(f"  {'-' * 40} {'-' * 22}")
    for check in report["checks"]:
        print(f"  {check['check']:<40} {check['verdict']:<22}")
    print()
