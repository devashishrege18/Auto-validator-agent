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
import hashlib
import requests
from datetime import datetime, timezone
from typing import Any, Optional

from validator.task_profiles import classify_task, get_profile, score_evidence

# -------------------------------------------------------
# Ollama Configuration
# -------------------------------------------------------
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODELS = ["phi3", "llama3", "mistral"]  # Fallback chain
OLLAMA_MODEL = OLLAMA_MODELS[0]
OLLAMA_TIMEOUT = 300  # seconds — phi3 on CPU can be slow

# -------------------------------------------------------
# LLM Response Cache (avoids re-calling for same inputs)
# -------------------------------------------------------
_llm_cache: dict[str, str] = {}
MAX_CACHE_SIZE = 100


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

    # ----- 7. Timestamp anomaly -----
    # Evidence submitted outside business hours or in the future
    submitted_at = evidence.get("submitted_at", "")
    if submitted_at:
        try:
            ts = datetime.fromisoformat(str(submitted_at).replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if ts > now:
                suspicions.append({
                    "flag": "TIMESTAMP_ANOMALY",
                    "detail": (
                        f"Evidence timestamp ({submitted_at}) is in the future. "
                        "Possible clock manipulation or fabricated evidence."
                    ),
                    "weight": 20,
                })
            elif ts.hour < 4 or ts.hour > 23:
                suspicions.append({
                    "flag": "TIMESTAMP_ANOMALY",
                    "detail": (
                        f"Evidence submitted at unusual hour ({ts.hour}:00). "
                        "Activity outside business hours may indicate automation."
                    ),
                    "weight": 10,
                })
        except (ValueError, TypeError):
            pass  # Can't parse timestamp — not suspicious on its own

    # ----- 8. API unavailable during claimed completion -----
    # Manual says "Done" but API returned None (unreachable)
    api_unavailable = evidence.get("api_unavailable", False)
    if (manual_status in ("done", "completed", "yes", "true")
            and (api_unavailable is True or evidence.get("api_error"))):
        suspicions.append({
            "flag": "API_UNAVAILABLE_BYPASS",
            "detail": (
                "Task was marked complete while API verification was "
                "unavailable. Possible attempt to bypass automated checks "
                "during a system outage window."
            ),
            "weight": 25,
        })

    # ----- 9. Cross-field inconsistency -----
    # Reviewer present but no document, or document but no reviewer
    has_reviewer = bool(evidence.get("reviewer"))
    has_document = bool(evidence.get("document_id"))
    if has_reviewer and not has_document:
        suspicions.append({
            "flag": "CROSS_FIELD_MISMATCH",
            "detail": (
                "A reviewer is listed but no document_id was provided. "
                "What exactly did the reviewer review?"
            ),
            "weight": 10,
        })
    elif has_document and not has_reviewer:
        suspicions.append({
            "flag": "CROSS_FIELD_MISMATCH",
            "detail": (
                "A document_id is present but no reviewer signed off. "
                "Documents should have reviewer attestation."
            ),
            "weight": 10,
        })

    # ----- 10. Suspiciously fast completion -----
    completed_at = evidence.get("completed_at", "")
    created_at = evidence.get("created_at", "")
    if completed_at and created_at:
        try:
            t_start = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
            t_end = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
            delta_minutes = (t_end - t_start).total_seconds() / 60
            if 0 < delta_minutes < 5:
                suspicions.append({
                    "flag": "SUSPICIOUSLY_FAST",
                    "detail": (
                        f"Task completed in {delta_minutes:.0f} minutes. "
                        "Complex compliance tasks typically take much longer."
                    ),
                    "weight": 15,
                })
        except (ValueError, TypeError):
            pass

    # ----- 11. Duplicate evidence (same doc reused) -----
    doc_id = evidence.get("document_id", "")
    if doc_id and str(doc_id).startswith("REUSED-"):
        suspicions.append({
            "flag": "DUPLICATE_EVIDENCE",
            "detail": (
                f"Document '{doc_id}' appears to be reused from another task. "
                "Each compliance task should have unique evidence."
            ),
            "weight": 15,
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
    Build a structured prompt with banking-specific system
    context and few-shot examples for consistent output.
    """
    # Classify the task for context-aware prompting
    category = classify_task(task)
    profile = get_profile(category)

    evidence_text = json.dumps(evidence, indent=2, default=str)

    if suspicions:
        suspicion_text = "\n".join(
            f"  - [{s['flag']}] {s['detail']}" for s in suspicions
        )
    else:
        suspicion_text = "  None detected — evidence appears clean."

    prompt = f"""You are a senior banking compliance auditor specialising in PCI-DSS, NIST SP 800-63B, RBI Cybersecurity Framework, and ISO 27001.

TASK CATEGORY: {category.upper()} — {profile['description']}

TASK: {task}

EVIDENCE PROVIDED:
{evidence_text}

AUTOMATED SUSPICION FLAGS:
{suspicion_text}

=== FEW-SHOT EXAMPLES ===

Example 1 (VERIFIED):
Task: "Enable MFA for admin accounts"
Evidence: {{"api_response": true, "manual_status": "Done", "reviewer": "Amit"}}
Flags: None
Response: {{"status": "VERIFIED", "reason": "API confirms MFA is active and reviewer has attested.", "concerns": [], "recommendation": "No action needed."}}

Example 2 (NON_COMPLIANT):
Task: "Activate perimeter firewall"
Evidence: {{"api_response": false, "manual_status": "Done"}}
Flags: [CONTRADICTORY_EVIDENCE]
Response: {{"status": "NON_COMPLIANT", "reason": "API shows firewall inactive despite manual claim of completion — evidence contradicts.", "concerns": ["Manual bypass suspected", "PCI-DSS 1.1 violation"], "recommendation": "Escalate immediately. Verify firewall config."}}

=== YOUR ANALYSIS ===
Respond ONLY with valid JSON in this exact format:
{{
  "status": "VERIFIED or NON_COMPLIANT or NEEDS_REVIEW",
  "reason": "One clear sentence explaining your verdict",
  "concerns": ["list", "of", "specific", "concerns"],
  "recommendation": "One sentence for the audit team"
}}"""

    return prompt


# -------------------------------------------------------
# 5. OLLAMA CALLER
# -------------------------------------------------------

def call_ollama(prompt: str) -> Optional[str]:
    """
    Send the reasoning prompt to Ollama with:
      - Response caching (same prompt = cached result)
      - Multi-model fallback (phi3 → llama3 → mistral)

    Returns None if all models fail or Ollama is unavailable.
    """
    global OLLAMA_MODEL, _llm_cache

    # Check cache first
    cache_key = hashlib.md5(prompt.encode()).hexdigest()
    if cache_key in _llm_cache:
        print("[REASONING] Cache hit — returning cached LLM response")
        return _llm_cache[cache_key]

    # Try each model in the fallback chain
    for model in OLLAMA_MODELS:
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "top_p": 0.9,
                        "num_predict": 512,
                    },
                },
                timeout=OLLAMA_TIMEOUT,
            )

            if response.status_code == 200:
                result = response.json().get("response", "")
                OLLAMA_MODEL = model  # Track which model succeeded
                # Store in cache
                if len(_llm_cache) >= MAX_CACHE_SIZE:
                    _llm_cache.clear()
                _llm_cache[cache_key] = result
                print(f"[REASONING] Got response from {model}")
                return result
            else:
                print(f"[REASONING] {model} error {response.status_code}, trying next...")
                continue

        except requests.ConnectionError:
            print("[REASONING] Ollama not running at", OLLAMA_URL)
            return None  # No point trying other models if Ollama is down
        except requests.Timeout:
            print(f"[REASONING] {model} timed out, trying next...")
            continue
        except Exception as e:
            print(f"[REASONING] {model} error: {e}, trying next...")
            continue

    print("[REASONING] All models failed")
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

    Orchestrates the full validation pipeline with an
    explainable reasoning chain:
    1. Classify the task category (context-aware)
    2. Score evidence using category-specific weights
    3. Detect suspicions (deterministic)
    4. Calculate risk and confidence scores
    5. Call LLM for intelligent reasoning (or fallback)
    6. Evaluate watchdog alerts
    7. Return standardised result with full reasoning chain
    """
    from validator.watchdog import evaluate_alert

    timestamp = datetime.now(timezone.utc).isoformat()
    reasoning_chain = []

    # --------------------------------------------------
    # Step 1: Classify the task category
    # --------------------------------------------------
    category = classify_task(task)
    profile = get_profile(category)
    reasoning_chain.append({
        "step": 1,
        "action": "classify_task",
        "result": category,
        "note": f"Task matched '{category}' profile — {profile['description'][:80]}",
    })

    # --------------------------------------------------
    # Step 2: Context-aware evidence scoring
    # --------------------------------------------------
    evidence_score = score_evidence(evidence or {}, category)
    reasoning_chain.append({
        "step": 2,
        "action": "score_evidence",
        "result": {
            "weighted_score": evidence_score["weighted_score"],
            "quality": evidence_score["evidence_quality"],
            "missing_critical": evidence_score["missing_critical"],
        },
        "note": (
            f"Evidence quality: {evidence_score['evidence_quality']} "
            f"({evidence_score['weighted_score']:.0%})"
        ),
    })

    # --------------------------------------------------
    # Step 3: Deterministic suspicion detection
    # --------------------------------------------------
    suspicions = detect_suspicions(task, evidence)
    reasoning_chain.append({
        "step": 3,
        "action": "detect_suspicions",
        "result": f"{len(suspicions)} flag(s)",
        "note": (
            f"Flags: {', '.join(s['flag'] for s in suspicions)}"
            if suspicions else "No suspicious patterns detected"
        ),
    })

    # --------------------------------------------------
    # Step 4: Calculate scores
    # --------------------------------------------------
    risk_score = calculate_risk_score(suspicions)
    confidence_score = calculate_confidence(evidence, suspicions)

    # Context-aware adjustment: if evidence quality is weak
    # for a high-threshold category, lower confidence
    if (evidence_score["weighted_score"] < 0.4
            and confidence_score > profile["min_confidence"]):
        confidence_score = max(30, confidence_score - 15)

    reasoning_chain.append({
        "step": 4,
        "action": "calculate_scores",
        "result": {"confidence": confidence_score, "risk": risk_score},
        "note": (
            f"Confidence: {confidence_score}%, Risk: {risk_score}/100 "
            f"(threshold: {profile['min_confidence']}%)"
        ),
    })

    # --------------------------------------------------
    # Step 5: LLM reasoning (with deterministic fallback)
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

            if status not in (VERIFIED, NON_COMPLIANT, NEEDS_REVIEW):
                status = NEEDS_REVIEW

            # Confidence calibration: LLM vs rules agreement
            if suspicions and status == VERIFIED:
                confidence_score = max(30, confidence_score - 20)
            elif not suspicions and status == VERIFIED:
                confidence_score = min(98, confidence_score + 10)

            reasoning_chain.append({
                "step": 5,
                "action": "llm_reasoning",
                "result": status,
                "note": f"LLM ({OLLAMA_MODEL}) verdict: {status} — {reason[:80]}",
            })
        else:
            fallback = deterministic_verdict(
                task, evidence, suspicions, risk_score
            )
            status = fallback["status"]
            reason = fallback["reason"] + " (LLM response unparseable)"
            concerns = fallback["concerns"]
            recommendation = fallback["recommendation"]
            reasoning_chain.append({
                "step": 5,
                "action": "deterministic_fallback",
                "result": status,
                "note": "LLM responded but output was unparseable — used rules",
            })
    else:
        fallback = deterministic_verdict(
            task, evidence, suspicions, risk_score
        )
        status = fallback["status"]
        reason = fallback["reason"]
        concerns = fallback["concerns"]
        recommendation = fallback["recommendation"]
        reasoning_chain.append({
            "step": 5,
            "action": "deterministic_fallback",
            "result": status,
            "note": "LLM unavailable — used deterministic rules only",
        })

    # --------------------------------------------------
    # Step 6: Determine severity level
    # --------------------------------------------------
    if risk_score >= 70 or status == NON_COMPLIANT:
        severity = "CRITICAL"
    elif risk_score >= 40 or len(suspicions) >= 2:
        severity = "HIGH"
    elif risk_score >= 20 or suspicions:
        severity = "MEDIUM"
    else:
        severity = "LOW"

    reasoning_chain.append({
        "step": 6,
        "action": "determine_severity",
        "result": severity,
        "note": f"Severity: {severity} (risk={risk_score}, flags={len(suspicions)})",
    })

    # --------------------------------------------------
    # Step 7: Build the standardised result
    # --------------------------------------------------
    result = {
        "task_id": task_id,
        "status": status,
        "confidence_score": confidence_score,
        "risk_score": risk_score,
        "reason": reason,
        "concerns": concerns,
        "recommendation": recommendation,
        "suspicion_flags": [s["flag"] for s in suspicions],
        "severity": severity,
        "task_category": category,
        "evidence_quality": evidence_score["evidence_quality"],
        "reasoning_chain": reasoning_chain,
        "llm_used": llm_used,
        "llm_model": OLLAMA_MODEL if llm_used else None,
        "timestamp": timestamp,
    }

    # --------------------------------------------------
    # Step 8: Evaluate watchdog alert
    # --------------------------------------------------
    watchdog = evaluate_alert(result)
    result["watchdog_alert"] = watchdog["watchdog_alert"]
    result["alert_level"] = watchdog["alert_level"]

    return result
