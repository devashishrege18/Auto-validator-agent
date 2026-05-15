# -------------------------------------------------------
# demo.py
# -------------------------------------------------------
# Hackathon Demo Script for the Auto-Auditor Validator Agent.
#
# Simulates the full multi-agent workflow:
#   Dispatcher Agent  →  Validator Agent  →  Watchdog/Sentinel
#
# Runs 7 realistic banking compliance scenarios and shows:
#   - Context-aware task classification
#   - Contradiction detection with reasoning chain
#   - Watchdog alert escalation
#   - Standardised API response envelopes
#
# Prerequisites:
#   1. Server running:  uvicorn main:app --reload
#   2. (Optional) Ollama:  ollama serve
#
# Usage:
#   python demo.py
# -------------------------------------------------------

import requests
import json
import time
import sys

BASE_URL = "http://127.0.0.1:8000"
TIMEOUT = 300


# -------------------------------------------------------
# Demo Scenarios — 7 realistic banking compliance cases
# -------------------------------------------------------

SCENARIOS = [
    {
        "phase": "DISPATCHER → VALIDATOR",
        "title": "✅ Scenario 1: Clean MFA Compliance",
        "description": "API confirms MFA active, reviewer signed off, full evidence.",
        "payload": {
            "task_id": 1,
            "task": "Enable Multi-Factor Authentication for all admin accounts",
            "evidence": {
                "api_response": True,
                "manual_status": "Done",
                "screenshot_uploaded": True,
                "reviewer": "Amit Verma",
                "document_id": "DOC-MFA-2026",
            }
        },
        "expected": "VERIFIED",
    },
    {
        "phase": "DISPATCHER → VALIDATOR",
        "title": "🔴 Scenario 2: Firewall Contradiction",
        "description": "Someone says 'Done' but API shows firewall is OFF — classic bypass attempt.",
        "payload": {
            "task_id": 2,
            "task": "Activate perimeter firewall for cardholder data zone",
            "evidence": {
                "api_response": False,
                "manual_status": "Done",
                "screenshot_uploaded": False,
            }
        },
        "expected": "NON_COMPLIANT",
    },
    {
        "phase": "DISPATCHER → VALIDATOR",
        "title": "🔴 Scenario 3: Zero Evidence — Ghost Completion",
        "description": "AML review claimed complete but zero evidence provided.",
        "payload": {
            "task_id": 3,
            "task": "Complete Anti-Money Laundering transaction review for Q1",
            "evidence": {}
        },
        "expected": "NON_COMPLIANT",
    },
    {
        "phase": "DISPATCHER → VALIDATOR",
        "title": "🟡 Scenario 4: Manual-Only — No API Backup",
        "description": "Password policy claimed done with screenshot but no API verification.",
        "payload": {
            "task_id": 4,
            "task": "Enforce 12-character minimum password policy across all systems",
            "evidence": {
                "manual_status": "Completed",
                "screenshot_uploaded": True,
            }
        },
        "expected": "NEEDS_REVIEW",
    },
    {
        "phase": "DISPATCHER → VALIDATOR",
        "title": "🟡 Scenario 5: Suspicious Timing — After-Hours Completion",
        "description": "Training submitted at 2 AM with suspiciously fast completion.",
        "payload": {
            "task_id": 5,
            "task": "Complete cybersecurity awareness training for Q2",
            "evidence": {
                "manual_status": "Done",
                "document_id": "CERT-2026-Q2",
                "submitted_at": "2026-05-15T02:15:00+00:00",
                "created_at": "2026-05-15T02:12:00+00:00",
                "completed_at": "2026-05-15T02:15:00+00:00",
            }
        },
        "expected": "NEEDS_REVIEW",
    },
    {
        "phase": "DISPATCHER → VALIDATOR",
        "title": "🔴 Scenario 6: API Outage Bypass",
        "description": "Task completed during known API outage — possible evasion.",
        "payload": {
            "task_id": 6,
            "task": "Enable MFA for contractor VPN access",
            "evidence": {
                "manual_status": "Done",
                "api_unavailable": True,
                "api_error": "Connection refused",
                "screenshot_uploaded": True,
            }
        },
        "expected": "NON_COMPLIANT",
    },
    {
        "phase": "DISPATCHER → VALIDATOR",
        "title": "🟡 Scenario 7: Cross-Field Mismatch",
        "description": "Reviewer listed but no document — what did they review?",
        "payload": {
            "task_id": 7,
            "task": "Conduct KYC document verification for new accounts",
            "evidence": {
                "api_response": True,
                "reviewer": "Neha Kulkarni",
            }
        },
        "expected": "VERIFIED (with note)",
    },
]


# -------------------------------------------------------
# Pretty Print Helpers
# -------------------------------------------------------

DIVIDER = "═" * 72
THIN = "─" * 72

def c(text, color):
    """Colorize text for terminal output."""
    colors = {
        "green": "\033[92m", "red": "\033[91m", "yellow": "\033[93m",
        "cyan": "\033[96m", "bold": "\033[1m", "dim": "\033[2m",
        "reset": "\033[0m",
    }
    return f"{colors.get(color, '')}{text}{colors['reset']}"


def print_banner():
    print()
    print(c(DIVIDER, "cyan"))
    print(c("  🏦  AUTO-AUDITOR VALIDATOR AGENT — LIVE DEMO", "bold"))
    print(c("  Hybrid Deterministic + LLM Compliance Verification", "dim"))
    print(c("  Simulating: Dispatcher → Validator → Watchdog Flow", "dim"))
    print(c(DIVIDER, "cyan"))
    print()


def print_phase(scenario, index):
    print(c(THIN, "dim"))
    print(c(f"  [{scenario['phase']}]", "cyan"))
    print(c(f"  {scenario['title']}", "bold"))
    print(f"  {scenario['description']}")
    print(f"  Expected: {scenario['expected']}")
    print(c(THIN, "dim"))


def print_result(data):
    """Print a validation result from the API envelope."""
    status = data.get("status", "UNKNOWN")
    icon = {"VERIFIED": "✅", "NON_COMPLIANT": "❌", "NEEDS_REVIEW": "🔍"}.get(status, "❓")
    severity = data.get("severity", "?")
    sev_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(severity, "dim")

    print(f"\n  {icon} Verdict:     {c(status, 'bold')}")
    print(f"  📊 Confidence:  {data.get('confidence_score', 0)}%")
    print(f"  ⚠️  Risk:        {data.get('risk_score', 0)}/100")
    print(f"  🏷️  Category:    {data.get('task_category', '?')}")
    print(f"  🔺 Severity:    {c(severity, sev_color)}")
    print(f"  📝 Quality:     {data.get('evidence_quality', '?')}")
    print(f"  🤖 LLM Used:    {'Yes (' + str(data.get('llm_model', '?')) + ')' if data.get('llm_used') else 'No (deterministic)'}")

    flags = data.get("suspicion_flags", [])
    if flags:
        print(f"  🚩 Flags:       {c(', '.join(flags), 'yellow')}")

    print(f"\n  💬 Reason: {data.get('reason', 'N/A')}")

    concerns = data.get("concerns", [])
    if concerns:
        print("  ⚡ Concerns:")
        for con in concerns[:3]:
            print(f"     • {con}")

    recommendation = data.get("recommendation", "")
    if recommendation:
        print(f"  🎯 Action: {recommendation}")

    # Show watchdog alert if triggered
    if data.get("watchdog_alert"):
        level = data.get("alert_level", "?")
        alert_color = {"CRITICAL": "red", "WARNING": "yellow"}.get(level, "cyan")
        print(f"\n  {c('🔔 WATCHDOG ALERT: ' + level, alert_color)}")

    # Show reasoning chain (abbreviated)
    chain = data.get("reasoning_chain", [])
    if chain:
        print(f"\n  📋 Reasoning Chain ({len(chain)} steps):")
        for step in chain:
            print(f"     {step['step']}. [{step['action']}] → {step.get('note', '')[:65]}")

    print()


def print_watchdog_summary():
    """Fetch and display watchdog status."""
    try:
        r = requests.get(f"{BASE_URL}/watchdog/status", timeout=10)
        body = r.json()
        summary = body.get("data", body)

        status = summary.get("status", "?")
        status_icon = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(status, "⚪")
        status_color = {"green": "green", "yellow": "yellow", "red": "red"}.get(status, "dim")

        print(c(DIVIDER, "cyan"))
        print(c("  🛡️  WATCHDOG STATUS (Spectre-Sentinel)", "bold"))
        print(c(DIVIDER, "cyan"))
        print(f"\n  Overall:   {status_icon} {c(status.upper(), status_color)}")
        print(f"  Critical:  {summary.get('critical_count', 0)}")
        print(f"  Warnings:  {summary.get('warning_count', 0)}")
        print(f"  Info:      {summary.get('info_count', 0)}")
        print(f"  Total:     {summary.get('total_alerts', 0)}")
        print()
    except Exception:
        print("  (Could not fetch watchdog status)")


def print_audit_summary():
    """Fetch and display audit trail stats."""
    try:
        r = requests.get(f"{BASE_URL}/audit-stats", timeout=10)
        body = r.json()
        stats = body.get("data", body)

        print(c(DIVIDER, "cyan"))
        print(c("  📊 AUDIT TRAIL SUMMARY", "bold"))
        print(c(DIVIDER, "cyan"))
        print(f"\n  Total Validations:  {stats.get('total_validations', 0)}")
        print(f"  Avg Risk Score:     {stats.get('avg_risk_score', 0)}")
        print(f"  High Risk Count:    {stats.get('high_risk_count', 0)}")

        counts = stats.get("status_counts", {})
        if counts:
            print("\n  Verdict Breakdown:")
            for status, count in counts.items():
                print(f"    {status}: {count}")
        print()
    except Exception:
        print("  (Could not fetch audit stats)")


# -------------------------------------------------------
# Main Demo Runner
# -------------------------------------------------------

def run_demo():
    print_banner()

    # Check server
    print("  🔌 Checking connectivity...")
    try:
        r = requests.get(f"{BASE_URL}/", timeout=5)
        print(f"  ✅ Server: ONLINE ({BASE_URL})")
    except requests.ConnectionError:
        print(c(f"  ❌ Server not running at {BASE_URL}", "red"))
        print(f"     Start it with: uvicorn main:app --reload")
        sys.exit(1)

    # Check Ollama
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"  ✅ Ollama: ONLINE ({', '.join(models[:3]) or 'no models'})")
    except Exception:
        print(f"  ⚠️  Ollama: OFFLINE (using deterministic fallback)")

    print(f"\n  Running {len(SCENARIOS)} compliance scenarios...")
    print(f"  (LLM calls may take 30-60s on CPU)\n")

    # Run each scenario
    for i, scenario in enumerate(SCENARIOS):
        print_phase(scenario, i)

        start = time.time()
        try:
            r = requests.post(
                f"{BASE_URL}/reasoning-validate",
                json=scenario["payload"],
                timeout=TIMEOUT,
            )
            elapsed = time.time() - start

            if r.status_code == 200:
                body = r.json()
                # Handle both envelope and raw responses
                data = body.get("data", body)
                print_result(data)
                print(c(f"  ⏱️  Completed in {elapsed:.1f}s", "dim"))
            else:
                print(c(f"  ❌ HTTP {r.status_code}: {r.text[:200]}", "red"))

        except requests.Timeout:
            print(c(f"  ⏱️  TIMEOUT (>{TIMEOUT}s) — try again", "yellow"))
        except Exception as e:
            print(c(f"  ❌ Error: {e}", "red"))

        print()

    # Print summaries
    print_watchdog_summary()
    print_audit_summary()

    print(c(DIVIDER, "cyan"))
    print(c("  ✅ DEMO COMPLETE!", "bold"))
    print()
    print(f"  Interactive docs:  {BASE_URL}/docs")
    print(f"  Audit trail:       {BASE_URL}/audit-trail")
    print(f"  Watchdog alerts:   {BASE_URL}/watchdog/alerts")
    print(f"  Watchdog status:   {BASE_URL}/watchdog/status")
    print(c(DIVIDER, "cyan"))
    print()


if __name__ == "__main__":
    run_demo()
