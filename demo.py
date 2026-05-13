# -------------------------------------------------------
# demo.py
# -------------------------------------------------------
# Run this script to demo the Auto-Auditor Validator Agent.
#
# It sends 5 realistic compliance scenarios to the
# /reasoning-validate endpoint and displays the results
# in a clean, presentation-ready format.
#
# Prerequisites:
#   1. Server running:  uvicorn main:app --reload
#   2. Ollama running:  ollama serve  (or running as service)
#
# Usage:
#   python demo.py
# -------------------------------------------------------

import requests
import json
import time
import sys

# -------------------------------------------------------
# Configuration
# -------------------------------------------------------
BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 300  # LLM can take a minute on CPU


# -------------------------------------------------------
# Demo Test Scenarios
# -------------------------------------------------------
# These are designed to show off every capability of
# the reasoning engine — from clean passes to
# suspicious contradictions.
# -------------------------------------------------------

SCENARIOS = [
    {
        "title": "SCENARIO 1: Clean Compliance (should VERIFY)",
        "description": "MFA enabled — API confirms, manual confirms, screenshot uploaded.",
        "payload": {
            "task_id": 1,
            "task": "Enable MFA for all admin accounts",
            "evidence": {
                "api_response": True,
                "manual_status": "Done",
                "screenshot_uploaded": True,
                "reviewer": "Amit Verma"
            }
        }
    },
    {
        "title": "SCENARIO 2: Contradictory Evidence (should flag NON_COMPLIANT)",
        "description": "Firewall — someone says 'Done' manually but API says it's still OFF.",
        "payload": {
            "task_id": 2,
            "task": "Activate perimeter firewall for cardholder data zone",
            "evidence": {
                "api_response": False,
                "manual_status": "Done",
                "screenshot_uploaded": False
            }
        }
    },
    {
        "title": "SCENARIO 3: No Evidence At All (should flag NON_COMPLIANT)",
        "description": "AML review — task claimed complete but zero evidence provided.",
        "payload": {
            "task_id": 3,
            "task": "Complete Anti-Money Laundering transaction review for Q1",
            "evidence": {}
        }
    },
    {
        "title": "SCENARIO 4: Suspicious — Manual Only (should flag NEEDS_REVIEW)",
        "description": "Password policy — someone says it's done but no API verification exists.",
        "payload": {
            "task_id": 4,
            "task": "Enforce 12-character minimum password policy",
            "evidence": {
                "manual_status": "Completed",
                "screenshot_uploaded": True
            }
        }
    },
    {
        "title": "SCENARIO 5: API Confirms But No Supporting Docs (should VERIFY with note)",
        "description": "KYC check — API says compliant but no documents or reviewer recorded.",
        "payload": {
            "task_id": 5,
            "task": "Verify KYC documentation for new corporate accounts",
            "evidence": {
                "api_response": True,
                "manual_status": "Done"
            }
        }
    },
]


# -------------------------------------------------------
# Display Helpers
# -------------------------------------------------------

def print_header():
    """Print a nice demo header."""
    print()
    print("=" * 70)
    print("    AUTO-AUDITOR VALIDATOR AGENT — LIVE DEMO")
    print("    Hybrid Deterministic + LLM Compliance Reasoning")
    print("=" * 70)
    print()


def print_scenario_header(scenario):
    """Print the scenario title and description."""
    print("-" * 70)
    print(f"  {scenario['title']}")
    print(f"  {scenario['description']}")
    print("-" * 70)


def print_result(result):
    """Print the validation result in a clean format."""
    status = result.get("status", "UNKNOWN")
    confidence = result.get("confidence_score", 0)
    risk = result.get("risk_score", 0)
    reason = result.get("reason", "No reason provided.")
    flags = result.get("suspicion_flags", [])
    llm = result.get("llm_used", False)
    concerns = result.get("concerns", [])
    recommendation = result.get("recommendation", "")

    # Status with visual indicator
    status_icon = {
        "VERIFIED": "[PASS]",
        "NON_COMPLIANT": "[FAIL]",
        "NEEDS_REVIEW": "[REVIEW]",
    }.get(status, "[????]")

    print()
    print(f"  Status:      {status_icon} {status}")
    print(f"  Confidence:  {confidence}%")
    print(f"  Risk Score:  {risk}/100")
    print(f"  LLM Used:    {'Yes (phi3)' if llm else 'No (deterministic only)'}")

    if flags:
        print(f"  Suspicions:  {', '.join(flags)}")

    print()
    print(f"  Reason: {reason}")

    if concerns:
        print(f"  Concerns:")
        for c in concerns:
            print(f"    - {c}")

    if recommendation:
        print(f"  Action: {recommendation}")

    print()


def print_audit_summary():
    """Print the audit trail summary."""
    try:
        r = requests.get(f"{BASE_URL}/audit-stats", timeout=10)
        stats = r.json()

        print("=" * 70)
        print("    AUDIT TRAIL SUMMARY")
        print("=" * 70)
        print()
        print(f"  Total Validations:  {stats.get('total_validations', 0)}")
        print(f"  Avg Risk Score:     {stats.get('avg_risk_score', 0)}")
        print(f"  High Risk Count:    {stats.get('high_risk_count', 0)}")
        print()

        counts = stats.get("status_counts", {})
        for status, count in counts.items():
            print(f"    {status}: {count}")

        print()
    except Exception:
        print("  (Could not fetch audit stats)")


# -------------------------------------------------------
# Main Demo Runner
# -------------------------------------------------------

def run_demo():
    """Run all demo scenarios sequentially."""

    print_header()

    # Check if server is running
    print("  Checking server connectivity...")
    try:
        r = requests.get(f"{BASE_URL}/", timeout=5)
        print(f"  Server: ONLINE ({BASE_URL})")
    except requests.ConnectionError:
        print(f"  ERROR: Server not running at {BASE_URL}")
        print(f"  Start it with: uvicorn main:app --reload")
        sys.exit(1)

    # Check if Ollama is running
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        print(f"  Ollama: ONLINE (phi3 local LLM)")
    except requests.ConnectionError:
        print(f"  Ollama: OFFLINE (will use deterministic fallback)")

    print()
    print(f"  Running {len(SCENARIOS)} compliance scenarios...")
    print(f"  (Each may take 30-60s for LLM reasoning on CPU)")
    print()

    # Run each scenario
    for i, scenario in enumerate(SCENARIOS):
        print_scenario_header(scenario)

        start = time.time()
        try:
            r = requests.post(
                f"{BASE_URL}/reasoning-validate",
                json=scenario["payload"],
                timeout=TIMEOUT,
            )
            elapsed = time.time() - start

            if r.status_code == 200:
                result = r.json()
                print_result(result)
                print(f"  (Completed in {elapsed:.1f}s)")
            else:
                print(f"  ERROR: HTTP {r.status_code}")
                print(f"  {r.text[:200]}")

        except requests.Timeout:
            print(f"  TIMEOUT: LLM took too long (>{TIMEOUT}s)")
            print(f"  Try again — the first call is slowest.")

        except Exception as e:
            print(f"  ERROR: {e}")

        print()

    # Print audit summary
    print_audit_summary()

    print("=" * 70)
    print("    DEMO COMPLETE!")
    print()
    print("    Try it yourself:")
    print(f"    Swagger UI: {BASE_URL}/docs")
    print(f"    Audit Trail: {BASE_URL}/audit-trail")
    print("=" * 70)
    print()


# -------------------------------------------------------
# Entry Point
# -------------------------------------------------------
if __name__ == "__main__":
    run_demo()
