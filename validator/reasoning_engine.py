# -------------------------------------------------------
# validator/reasoning_engine.py
# -------------------------------------------------------
# The Reasoning Validator Engine — the intelligence layer
# that makes this system truly "agentic".
#
# Instead of simple if/else checks, this engine:
#   1. Runs deterministic suspicion detection first
#   2. Sends the evidence + suspicion flags to Ollama (phi3)
#   3. Parses the LLM's reasoning into a standardised result
#   4. Returns a structured verdict with confidence & risk scores
#
# The design is HYBRID:
#   • Deterministic rules catch obvious problems instantly
#   • LLM reasoning catches subtle contradictions and
#     provides human-readable explanations
#
# Architecture-ready for integration with:
#   • Dispatcher Agent (sends tasks here for validation)
#   • Spectre-Sentinel Watchdog (consumes risk scores)
#   • Unified frontend dashboard (displays verdicts)
# -------------------------------------------------------

import json
import re
import requests
from datetime import datetime, timezone
from typing import Any, Optional

# -------------------------------------------------------
# Ollama Configuration
# -------------------------------------------------------
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "phi3"
OLLAMA_TIMEOUT = 300  # seconds — phi3 on CPU can be slow


# -------------------------------------------------------
# Verdict Constants
# -------------------------------------------------------
VERIFIED = "VERIFIED"
NON_COMPLIANT = "NON_COMPLIANT"
NEEDS_REVIEW = "NEEDS_REVIEW"


# -------------------------------------------------------
# 1. SUSPICION DETECTOR (Deterministic Layer)
# -------------------------------------------------------
# These rules fire BEFORE the LLM is called. They catch
# obvious red flags and feed them as context to the LLM
# so it can reason about them more deeply.
# -------------------------------------------------------

def detect_suspicions(task: str, evidence: dict) -> list[dict]:
    """
    Run deterministic checks to detect suspicious patterns
    in the evidence before sending to the LLM.

    Each suspicion is a dict with:
        flag    — short identifier
        detail  — human-readable explanation
        weight  — how much this should increase the risk score (0-30)

    Parameters
    ----------
    task : str
        Description of the compliance task.
    evidence : dict
        Key-value pairs of evidence fields.

    Returns
    -------
    list[dict]
        List of detected suspicion flags (empty = clean).
    """
    suspicions = []

    # ----- 1. Missing evidence entirely -----
    # If evidence dict is empty or None, that's a major red flag
    if not evidence or len(evidence) == 0:
        suspicions.append({
            "flag": "NO_EVIDENCE",
            "detail": "No evidence was provided at all for this task.",
            "weight": 30,
        })
        return suspicions  # No point checking further

    # ----- 2. Manual completion without API verification -----
    # If someone says "Done" manually but the API check is missing
    # or False, that's suspicious — they might be lying.
    manual_status = evidence.get("manual_status", "").strip().lower()
    api_response = evidence.get("api_response")

    if manual_status in ("done", "completed", "yes", "true"):
        if api_response is None:
            suspicions.append({
                "flag": "MANUAL_WITHOUT_API",
                "detail": (
                    "Task marked as manually completed but no API "
                    "verification was provided. Cannot independently confirm."
                ),
                "weight": 20,
            })
        elif api_response is False or api_response == "false":
            suspicions.append({
                "flag": "CONTRADICTORY_EVIDENCE",
                "detail": (
                    "CONTRADICTION: Manual status says 'Done' but API "
                    "verification returned False. Evidence conflicts."
                ),
                "weight": 25,
            })

    # ----- 3. API says compliant but no supporting evidence -----
    # API returns True but there's no screenshot, document, or reviewer
    if api_response is True:
        has_supporting = any(
            evidence.get(key)
            for key in ["screenshot_uploaded", "document_id", "reviewer"]
        )
        if not has_supporting:
            suspicions.append({
                "flag": "API_ONLY_NO_SUPPORT",
                "detail": (
                    "API confirms compliance but no supporting evidence "
                    "(screenshot, document, or reviewer) was provided."
                ),
                "weight": 10,
            })

    # ----- 4. Screenshot uploaded but nothing else -----
    # Someone uploaded a screenshot but no API check and no reviewer
    screenshot = evidence.get("screenshot_uploaded")
    if screenshot is True and api_response is None and not evidence.get("reviewer"):
        suspicions.append({
            "flag": "SCREENSHOT_ONLY",
            "detail": (
                "Only a screenshot was provided as evidence. "
                "Screenshots can be fabricated — needs corroboration."
            ),
            "weight": 15,
        })

    # ----- 5. Key evidence fields are null/empty -----
    # Count how many evidence values are None, empty, or missing
    total_fields = len(evidence)
    empty_fields = sum(
        1 for v in evidence.values()
        if v is None or v == "" or v == "N/A"
    )

    if total_fields > 0 and empty_fields / total_fields > 0.5:
        suspicions.append({
            "flag": "MOSTLY_EMPTY",
            "detail": (
                f"{empty_fields}/{total_fields} evidence fields are "
                "empty or null. Insufficient data for confident verification."
            ),
            "weight": 15,
        })

    # ----- 6. API explicitly returned False -----
    if api_response is False:
        suspicions.append({
            "flag": "API_NEGATIVE",
            "detail": (
                "The API verification explicitly returned False. "
                "The compliance control is NOT in place."
            ),
            "weight": 25,
        })

    return suspicions


# -------------------------------------------------------
# 2. RISK SCORE CALCULATOR
# -------------------------------------------------------

def calculate_risk_score(suspicions: list[dict]) -> int:
    """
    Calculate a risk score (0-100) based on suspicion flags.

    0  = no risk (clean evidence)
    100 = maximum risk (highly suspicious)

    The score is the sum of suspicion weights, capped at 100.
    """
    if not suspicions:
        return 0

    raw_score = sum(s["weight"] for s in suspicions)
    return min(raw_score, 100)


# -------------------------------------------------------
# 3. CONFIDENCE SCORE CALCULATOR
# -------------------------------------------------------

def calculate_confidence(evidence: dict, suspicions: list[dict]) -> int:
    """
    Calculate how confident we are in the verdict (0-100).

    High confidence = lots of corroborating evidence, few suspicions.
    Low confidence  = sparse evidence, many contradictions.
    """
    if not evidence:
        return 10  # Very low confidence with no evidence

    # Start at 50 (neutral)
    score = 50

    # Boost for each non-empty evidence field (+10 each, max +30)
    filled = sum(
        1 for v in evidence.values()
        if v is not None and v != "" and v != "N/A"
    )
    score += min(filled * 10, 30)

    # Boost for API verification (+15)
    if evidence.get("api_response") is True:
        score += 15

    # Penalty for each suspicion (-10 each)
    score -= len(suspicions) * 10

    # Clamp to 0-100 range
    return max(5, min(100, score))


# -------------------------------------------------------
# 4. LLM PROMPT BUILDER
# -------------------------------------------------------

def build_reasoning_prompt(
    task: str,
    evidence: dict,
    suspicions: list[dict],
) -> str:
    """
    Build a structured prompt that gives the LLM all the
    context it needs to reason about the compliance task.
    """

    # Format evidence as readable text
    evidence_text = json.dumps(evidence, indent=2, default=str)

    # Format suspicions as a list
    if suspicions:
        suspicion_text = "\n".join(
            f"  - [{s['flag']}] {s['detail']}" for s in suspicions
        )
    else:
        suspicion_text = "  None detected — evidence appears clean."

    prompt = f"""You are an expert banking compliance auditor. Analyze the following task and evidence to determine if the compliance requirement is genuinely satisfied.

TASK: {task}

EVIDENCE PROVIDED:
{evidence_text}

SUSPICION FLAGS DETECTED BY AUTOMATED RULES:
{suspicion_text}

ANALYZE THE FOLLOWING:
1. Is the evidence sufficient to verify this task?
2. Are there any contradictions in the evidence?
3. Is the task truly compliant based on the evidence?
4. Does anything look suspicious or fabricated?

RESPOND IN EXACTLY THIS JSON FORMAT (no extra text):
{{
  "status": "VERIFIED or NON_COMPLIANT or NEEDS_REVIEW",
  "reason": "One clear sentence explaining your verdict",
  "concerns": ["list", "of", "specific", "concerns"],
  "recommendation": "One sentence recommendation for the audit team"
}}"""

    return prompt


# -------------------------------------------------------
# 5. OLLAMA CALLER
# -------------------------------------------------------

def call_ollama(prompt: str) -> Optional[str]:
    """
    Send the reasoning prompt to Ollama and return
    the raw response text.

    Returns None if Ollama is unavailable or errors out.
    """
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,    # Low = more deterministic
                    "top_p": 0.9,
                    "num_predict": 512,    # Keep response concise
                },
            },
            timeout=OLLAMA_TIMEOUT,
        )

        if response.status_code == 200:
            return response.json().get("response", "")
        else:
            print(f"[REASONING] Ollama error {response.status_code}")
            return None

    except requests.ConnectionError:
        print("[REASONING] Ollama not running at", OLLAMA_URL)
        return None
    except requests.Timeout:
        print(f"[REASONING] Ollama timed out ({OLLAMA_TIMEOUT}s)")
        return None
    except Exception as e:
        print(f"[REASONING] Unexpected error: {e}")
        return None


# -------------------------------------------------------
# 6. LLM RESPONSE PARSER
# -------------------------------------------------------

def parse_llm_response(raw: str) -> Optional[dict]:
    """
    Extract the JSON verdict from the LLM's response.

    The LLM sometimes wraps JSON in markdown code blocks
    or adds extra text. This parser handles those cases.
    """
    if not raw:
        return None

    try:
        # Try 1: Direct JSON parse
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    try:
        # Try 2: Extract JSON from markdown code block
        # Matches ```json {...} ``` or just {...}
        match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except json.JSONDecodeError:
        pass

    # Try 3: Find JSON with nested structures
    try:
        start = raw.index('{')
        # Find the matching closing brace
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == '{':
                depth += 1
            elif raw[i] == '}':
                depth -= 1
                if depth == 0:
                    return json.loads(raw[start:i+1])
    except (ValueError, json.JSONDecodeError):
        pass

    print(f"[REASONING] Could not parse LLM response as JSON")
    return None


# -------------------------------------------------------
# 7. FALLBACK REASONING (No LLM Available)
# -------------------------------------------------------

def deterministic_verdict(
    task: str,
    evidence: dict,
    suspicions: list[dict],
    risk_score: int,
) -> dict:
    """
    Generate a verdict using only deterministic rules
    when Ollama is not available.

    This ensures the system always returns a result,
    even without the LLM.
    """

    # High risk → NON_COMPLIANT
    if risk_score >= 50:
        status = NON_COMPLIANT
        reason = (
            f"Evidence has {len(suspicions)} suspicion flag(s) with a "
            f"combined risk score of {risk_score}/100. "
            f"Primary concern: {suspicions[0]['detail']}"
        )

    # Medium risk → NEEDS_REVIEW
    elif risk_score >= 20:
        status = NEEDS_REVIEW
        concerns = [s['flag'] for s in suspicions]
        reason = (
            f"Evidence partially supports compliance but "
            f"flagged concerns: {', '.join(concerns)}. "
            f"Manual review recommended."
        )

    # Low/no risk + API confirms → VERIFIED
    elif evidence.get("api_response") is True:
        status = VERIFIED
        reason = (
            "API verification confirms compliance. "
            "Evidence is consistent and no suspicions detected."
        )

    # No API but manual says done → NEEDS_REVIEW
    else:
        status = NEEDS_REVIEW
        reason = (
            "No API verification available. "
            "Cannot independently confirm compliance status."
        )

    return {
        "status": status,
        "reason": reason,
        "concerns": [s["detail"] for s in suspicions],
        "recommendation": (
            "No action needed." if status == VERIFIED
            else "Escalate to senior auditor for manual verification."
        ),
    }


# -------------------------------------------------------
# 8. MAIN REASONING FUNCTION
# -------------------------------------------------------

def reason_and_validate(
    task_id: int,
    task: str,
    evidence: dict,
) -> dict:
    """
    The main entry point for the Reasoning Validator Engine.

    Orchestrates the full validation pipeline:
    1. Detect suspicions (deterministic)
    2. Calculate risk and confidence scores
    3. Call LLM for intelligent reasoning (or fallback)
    4. Return standardised result

    Parameters
    ----------
    task_id : int
        Unique identifier for this task.
    task : str
        Description of the compliance task.
    evidence : dict
        Key-value evidence to validate against.

    Returns
    -------
    dict
        Standardised result with:
        - task_id, status, confidence_score, risk_score, reason
        - Plus: suspicion_flags, llm_used, timestamp
    """

    timestamp = datetime.now(timezone.utc).isoformat()

    # --------------------------------------------------
    # Step 1: Deterministic suspicion detection
    # --------------------------------------------------
    suspicions = detect_suspicions(task, evidence)

    # --------------------------------------------------
    # Step 2: Calculate scores
    # --------------------------------------------------
    risk_score = calculate_risk_score(suspicions)
    confidence_score = calculate_confidence(evidence, suspicions)

    # --------------------------------------------------
    # Step 3: LLM reasoning (with deterministic fallback)
    # --------------------------------------------------
    llm_used = False
    prompt = build_reasoning_prompt(task, evidence, suspicions)
    raw_llm = call_ollama(prompt)

    if raw_llm:
        llm_result = parse_llm_response(raw_llm)
        if llm_result:
            llm_used = True
            status = llm_result.get("status", NEEDS_REVIEW)
            reason = llm_result.get("reason", "LLM provided no reason.")
            concerns = llm_result.get("concerns", [])
            recommendation = llm_result.get(
                "recommendation",
                "Review LLM reasoning output."
            )

            # Validate the status is one of our expected values
            if status not in (VERIFIED, NON_COMPLIANT, NEEDS_REVIEW):
                status = NEEDS_REVIEW

            # Adjust confidence based on LLM agreement with rules
            if suspicions and status == VERIFIED:
                # LLM says verified but rules found issues — lower confidence
                confidence_score = max(30, confidence_score - 20)
            elif not suspicions and status == VERIFIED:
                # Both agree it's clean — boost confidence
                confidence_score = min(98, confidence_score + 10)
        else:
            # LLM responded but we couldn't parse it — use fallback
            fallback = deterministic_verdict(
                task, evidence, suspicions, risk_score
            )
            status = fallback["status"]
            reason = fallback["reason"] + " (LLM response unparseable)"
            concerns = fallback["concerns"]
            recommendation = fallback["recommendation"]
    else:
        # No LLM available — pure deterministic
        fallback = deterministic_verdict(
            task, evidence, suspicions, risk_score
        )
        status = fallback["status"]
        reason = fallback["reason"]
        concerns = fallback["concerns"]
        recommendation = fallback["recommendation"]

    # --------------------------------------------------
    # Step 4: Build the standardised result
    # --------------------------------------------------
    return {
        "task_id": task_id,
        "status": status,
        "confidence_score": confidence_score,
        "risk_score": risk_score,
        "reason": reason,
        "concerns": concerns,
        "recommendation": recommendation,
        "suspicion_flags": [s["flag"] for s in suspicions],
        "llm_used": llm_used,
        "llm_model": OLLAMA_MODEL if llm_used else None,
        "timestamp": timestamp,
    }
