# -------------------------------------------------------
# validator/llm_reasoner.py
# -------------------------------------------------------
# Local LLM reasoning engine using Ollama.
#
# This module calls the Ollama server running on your
# machine to generate natural-language audit reports.
# It takes the rule-based check results and ML predictions
# and asks the LLM to write an intelligent analysis.
#
# If Ollama is not running, the module falls back to
# template-based reasoning using the ML predictions.
#
# No external API keys needed — everything is local.
# -------------------------------------------------------

import json
import requests
from typing import Any, Optional

# -------------------------------------------------------
# Configuration
# -------------------------------------------------------
# Ollama runs a local HTTP server on this address.
# You can change the port if you configured Ollama
# differently.
OLLAMA_BASE_URL = "http://localhost:11434"

# The model to use for reasoning.
# phi3 is small (~2.3GB) and good at structured reasoning.
# Alternatives: "mistral", "llama3", "gemma"
OLLAMA_MODEL = "phi3"

# Timeout for the LLM call (seconds).
# LLM generation can take 30-60s on CPU, and the first
# call may be slower as Ollama loads the model into RAM.
OLLAMA_TIMEOUT = 300


# -------------------------------------------------------
# Ollama Availability Check
# -------------------------------------------------------

def is_ollama_available() -> bool:
    """
    Check if Ollama is running and accessible.

    Returns True if we can reach the Ollama server,
    False otherwise.
    """
    try:
        response = requests.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=5,
        )
        return response.status_code == 200
    except (requests.ConnectionError, requests.Timeout):
        return False


def get_available_models() -> list[str]:
    """
    Get the list of models available in Ollama.

    Returns
    -------
    list[str]
        Model names, e.g. ["phi3", "mistral", "llama3"]
    """
    try:
        response = requests.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=5,
        )
        if response.status_code == 200:
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        pass
    return []


# -------------------------------------------------------
# Prompt Construction
# -------------------------------------------------------

def build_audit_prompt(
    infrastructure_checks: list[dict],
    task_results: list[dict],
    ml_prediction: Optional[dict],
) -> str:
    """
    Build a detailed prompt for the LLM to generate
    a compliance audit report.

    The prompt includes:
    - All infrastructure check results
    - All task validation results
    - ML risk prediction (if available)
    - Instructions for structured output
    """

    # Build the infrastructure section
    infra_text = ""
    for check in infrastructure_checks:
        infra_text += (
            f"  - {check['check']}: {check['verdict']}\n"
            f"    Detail: {check['details']}\n"
        )

    # Build the task section
    task_text = ""
    for task in task_results:
        task_text += (
            f"  - {task.get('title', task.get('task_id', 'Unknown'))}: "
            f"{task.get('verdict', 'N/A')}\n"
        )
        reasons = task.get("reasons", [])
        for reason in reasons:
            task_text += f"    Reason: {reason}\n"

    # Build the ML prediction section
    ml_text = "  ML model not available.\n"
    if ml_prediction:
        ml_text = (
            f"  Risk Level: {ml_prediction['risk_level']} "
            f"(confidence: {ml_prediction['confidence']:.0%})\n"
            f"  Compliance Score: {ml_prediction['compliance_score']}/100\n"
            f"  Top factors: {json.dumps(dict(list(ml_prediction['feature_importances'].items())[:3]), indent=4)}\n"
        )

    prompt = f"""You are an expert banking compliance auditor. Analyse the following compliance check results and write a professional audit report.

## Infrastructure Compliance Checks
{infra_text}

## Task Validation Results
{task_text}

## ML Risk Assessment
{ml_text}

## Your Task
Write a concise but thorough audit report with these sections:

1. **Executive Summary** (2-3 sentences summarising the overall compliance posture)
2. **Critical Findings** (list each non-compliant item with its regulatory impact)
3. **Risk Assessment** (explain the combined risk, especially how multiple failures compound each other)
4. **Remediation Plan** (numbered list of prioritised actions, most urgent first)
5. **Positive Observations** (acknowledge what IS compliant — good audit practice)

Keep the tone professional but clear. Reference specific regulations where relevant (PCI-DSS, RBI guidelines, NIST SP 800-63B).
Be specific about WHY each finding matters and WHAT the consequences could be.
Do NOT use markdown headers — use plain text with numbered/bulleted lists."""

    return prompt


# -------------------------------------------------------
# LLM Reasoning (Ollama)
# -------------------------------------------------------

def call_ollama(prompt: str) -> Optional[str]:
    """
    Send a prompt to the local Ollama server and
    return the generated text.

    Parameters
    ----------
    prompt : str
        The full prompt to send to the LLM.

    Returns
    -------
    str | None
        The generated text, or None if the call failed.
    """
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.3,     # Low = more focused/deterministic
                    "top_p": 0.9,
                    "num_predict": 1024,    # Max tokens to generate
                },
            },
            timeout=OLLAMA_TIMEOUT,
        )

        if response.status_code == 200:
            data = response.json()
            return data.get("response", "")
        else:
            print(
                f"[LLM] Ollama returned status {response.status_code}: "
                f"{response.text[:200]}"
            )
            return None

    except requests.exceptions.ConnectionError:
        print("[LLM] Cannot connect to Ollama. Is it running?")
        return None

    except requests.exceptions.Timeout:
        print(f"[LLM] Ollama timed out after {OLLAMA_TIMEOUT}s.")
        return None

    except Exception as exc:
        print(f"[LLM] Unexpected error calling Ollama: {exc}")
        return None


# -------------------------------------------------------
# Template-Based Fallback Reasoning
# -------------------------------------------------------
# Used when Ollama is not available. Generates a
# structured report using pre-written templates and
# the ML prediction data.
# -------------------------------------------------------

def template_reasoning(
    infrastructure_checks: list[dict],
    task_results: list[dict],
    ml_prediction: Optional[dict],
) -> str:
    """
    Generate a template-based audit report when the
    LLM is not available.

    This produces a decent report using pre-written
    templates, but lacks the nuanced reasoning of an LLM.
    """
    lines = []

    # ----- Executive Summary -----
    lines.append("EXECUTIVE SUMMARY")
    lines.append("-" * 40)

    # Count verdicts
    verified = sum(1 for c in infrastructure_checks if c["verdict"] == "VERIFIED")
    non_compliant = sum(1 for c in infrastructure_checks if c["verdict"] == "NON-COMPLIANT")
    total_infra = len(infrastructure_checks)

    task_pass = sum(1 for t in task_results if t.get("verdict") == "PASS")
    task_fail = sum(1 for t in task_results if t.get("verdict") == "FAIL")
    task_review = sum(1 for t in task_results if t.get("verdict") == "NEEDS_REVIEW")
    total_tasks = len(task_results)

    if ml_prediction:
        risk = ml_prediction["risk_level"]
        score = ml_prediction["compliance_score"]
        lines.append(
            f"The organisation's compliance posture is assessed at "
            f"{risk} risk with a compliance score of {score}/100. "
            f"{verified}/{total_infra} infrastructure controls are verified "
            f"and {task_pass}/{total_tasks} tasks have full evidence."
        )
    else:
        lines.append(
            f"{verified}/{total_infra} infrastructure controls are verified "
            f"and {task_pass}/{total_tasks} tasks have full evidence."
        )

    lines.append("")

    # ----- Critical Findings -----
    lines.append("CRITICAL FINDINGS")
    lines.append("-" * 40)

    finding_num = 1
    for check in infrastructure_checks:
        if check["verdict"] == "NON-COMPLIANT":
            lines.append(f"{finding_num}. {check['check']}: {check['details']}")
            finding_num += 1

    for task in task_results:
        if task.get("verdict") == "FAIL":
            reasons = "; ".join(task.get("reasons", ["No details"]))
            lines.append(
                f"{finding_num}. {task.get('title', 'Unknown Task')}: {reasons}"
            )
            finding_num += 1

    if finding_num == 1:
        lines.append("No critical findings. All controls are compliant.")

    lines.append("")

    # ----- Risk Assessment -----
    lines.append("RISK ASSESSMENT")
    lines.append("-" * 40)

    if ml_prediction:
        lines.append(
            f"Risk Level: {ml_prediction['risk_level']} "
            f"(Model confidence: {ml_prediction['confidence']:.0%})"
        )
        lines.append(
            f"Compliance Score: {ml_prediction['compliance_score']}/100"
        )

        # Cross-control analysis
        features = ml_prediction.get("features_used", {})
        if features.get("mfa_enabled", 1) == 0 and features.get("firewall_active", 1) == 0:
            lines.append(
                "WARNING: Both MFA and firewall are non-compliant. "
                "This creates a compounding risk — the network perimeter "
                "is unprotected AND user authentication is weak, "
                "making the organisation vulnerable to both external "
                "attacks and credential-based breaches."
            )
    else:
        if non_compliant > 0:
            lines.append(
                f"{non_compliant} infrastructure control(s) are non-compliant. "
                "Manual risk assessment recommended."
            )
        else:
            lines.append("All infrastructure controls are compliant.")

    lines.append("")

    # ----- Remediation Plan -----
    lines.append("REMEDIATION PLAN")
    lines.append("-" * 40)

    action_num = 1
    # Prioritise by severity
    for check in infrastructure_checks:
        if check["verdict"] == "NON-COMPLIANT":
            if "Firewall" in check["check"]:
                lines.append(
                    f"{action_num}. [URGENT] Activate the perimeter firewall "
                    "immediately. Contact the network security team to "
                    "restore firewall rules and verify traffic filtering. "
                    "(PCI-DSS Requirement 1.1)"
                )
            elif "MFA" in check["check"]:
                lines.append(
                    f"{action_num}. [HIGH] Enable Multi-Factor Authentication "
                    "across all user accounts. Coordinate with the Identity "
                    "Provider team (Okta/Azure AD). (PCI-DSS Requirement 8.3)"
                )
            elif "Password" in check["check"]:
                lines.append(
                    f"{action_num}. [MEDIUM] Update the password policy to "
                    "enforce a minimum length of 12 characters with special "
                    "characters. (NIST SP 800-63B)"
                )
            else:
                lines.append(
                    f"{action_num}. Address: {check['check']} — {check['details']}"
                )
            action_num += 1

    for task in task_results:
        if task.get("verdict") == "FAIL":
            lines.append(
                f"{action_num}. Complete evidence for: "
                f"{task.get('title', 'Unknown Task')}"
            )
            action_num += 1

    if action_num == 1:
        lines.append("No remediation actions required at this time.")

    lines.append("")

    # ----- Positive Observations -----
    lines.append("POSITIVE OBSERVATIONS")
    lines.append("-" * 40)

    for check in infrastructure_checks:
        if check["verdict"] == "VERIFIED":
            lines.append(f"- {check['check']}: {check['details']}")

    for task in task_results:
        if task.get("verdict") == "PASS":
            lines.append(
                f"- {task.get('title', 'Unknown')}: "
                "Completed with full supporting evidence."
            )

    return "\n".join(lines)


# -------------------------------------------------------
# Main Reasoning Function
# -------------------------------------------------------

def generate_reasoning(
    infrastructure_checks: list[dict],
    task_results: list[dict],
    ml_prediction: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Generate an intelligent audit report using the
    best available reasoning engine.

    Priority:
    1. Ollama LLM (if available) — best quality
    2. Template-based fallback — always works

    Parameters
    ----------
    infrastructure_checks : list[dict]
        Results from check_mfa(), check_firewall(), etc.
    task_results : list[dict]
        Results from validate_task() for each task.
    ml_prediction : dict | None
        ML model predictions (risk level, score, etc.)

    Returns
    -------
    dict with keys:
        reasoning_mode : str — "llm" or "template"
        llm_model : str | None — which model was used
        audit_report : str — the generated report
    """

    # Try Ollama first
    if is_ollama_available():
        print("[LLM] Ollama is available. Generating LLM-powered report...")

        prompt = build_audit_prompt(
            infrastructure_checks, task_results, ml_prediction
        )

        llm_response = call_ollama(prompt)

        if llm_response:
            return {
                "reasoning_mode": "llm",
                "llm_model": OLLAMA_MODEL,
                "audit_report": llm_response.strip(),
            }
        else:
            print("[LLM] Ollama call failed. Falling back to templates.")

    else:
        print("[LLM] Ollama not available. Using template-based reasoning.")

    # Fallback to template-based reasoning
    report = template_reasoning(
        infrastructure_checks, task_results, ml_prediction
    )

    return {
        "reasoning_mode": "template",
        "llm_model": None,
        "audit_report": report,
    }
