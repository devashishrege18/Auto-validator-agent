# -------------------------------------------------------
# validator/task_profiles.py
# -------------------------------------------------------
# Context-Aware Task Classification & Validation Profiles.
#
# Different compliance tasks require different validation
# strategies. An MFA check should prioritize API evidence,
# while a training compliance task should prioritize
# attendance records and reviewer sign-off.
#
# This module provides:
#   1. A registry of task profiles with per-category
#      evidence weights and confidence thresholds
#   2. A keyword-based classifier that detects the task
#      category from the description text
#   3. A context-aware evidence scorer that applies the
#      correct weights for each task type
#
# WHY THIS MATTERS:
#   Without context-awareness, the validator treats a
#   firewall check and a training certificate the same —
#   which makes no sense in real-world compliance.
# -------------------------------------------------------

from typing import Optional


# -------------------------------------------------------
# Task Profile Registry
# -------------------------------------------------------
# Each profile defines:
#   keywords         — words that trigger this category
#   priority_evidence — which evidence fields matter most
#   weights          — how much each evidence type
#                      contributes to the confidence score
#   min_confidence   — minimum confidence threshold to
#                      auto-verify (below this → NEEDS_REVIEW)
#   severity_base    — default severity for violations
#   description      — human-readable explanation
# -------------------------------------------------------

TASK_PROFILES = {
    "mfa": {
        "keywords": [
            "mfa", "multi-factor", "multifactor", "two-factor",
            "2fa", "authentication", "otp", "authenticator",
        ],
        "priority_evidence": ["api_response"],
        "weights": {
            "api_response": 0.70,
            "manual_status": 0.10,
            "document": 0.10,
            "screenshot": 0.05,
            "reviewer": 0.05,
        },
        "min_confidence": 80,
        "severity_base": "HIGH",
        "description": (
            "MFA tasks require strong API-based verification. "
            "Manual claims without API confirmation are treated "
            "with high suspicion."
        ),
    },

    "firewall": {
        "keywords": [
            "firewall", "perimeter", "network security",
            "ids", "ips", "intrusion", "packet filter",
            "waf", "web application firewall",
        ],
        "priority_evidence": ["api_response", "config_snapshot"],
        "weights": {
            "api_response": 0.60,
            "manual_status": 0.05,
            "document": 0.20,
            "screenshot": 0.10,
            "reviewer": 0.05,
        },
        "min_confidence": 85,
        "severity_base": "CRITICAL",
        "description": (
            "Firewall tasks are critical infrastructure controls. "
            "API/config verification is essential — manual status "
            "alone is almost worthless."
        ),
    },

    "password": {
        "keywords": [
            "password", "passphrase", "credential",
            "password policy", "complexity", "rotation",
        ],
        "priority_evidence": ["api_response", "document_id"],
        "weights": {
            "api_response": 0.50,
            "manual_status": 0.15,
            "document": 0.20,
            "screenshot": 0.10,
            "reviewer": 0.05,
        },
        "min_confidence": 75,
        "severity_base": "HIGH",
        "description": (
            "Password policy tasks need system-level verification "
            "that the policy is actually enforced, not just written."
        ),
    },

    "training": {
        "keywords": [
            "training", "awareness", "certification",
            "course", "workshop", "seminar", "e-learning",
            "attendance", "compliance training",
        ],
        "priority_evidence": ["document_id", "reviewer"],
        "weights": {
            "api_response": 0.10,
            "manual_status": 0.25,
            "document": 0.35,
            "screenshot": 0.10,
            "reviewer": 0.20,
        },
        "min_confidence": 60,
        "severity_base": "MEDIUM",
        "description": (
            "Training tasks rely on documentation and reviewer "
            "sign-off. API verification is less relevant here. "
            "Manual completion claims are more acceptable."
        ),
    },

    "audit": {
        "keywords": [
            "audit", "review", "assessment", "inspection",
            "kyc", "aml", "anti-money", "due diligence",
            "dpia", "impact assessment", "regulatory",
        ],
        "priority_evidence": ["document_id", "reviewer"],
        "weights": {
            "api_response": 0.15,
            "manual_status": 0.15,
            "document": 0.35,
            "screenshot": 0.05,
            "reviewer": 0.30,
        },
        "min_confidence": 70,
        "severity_base": "HIGH",
        "description": (
            "Audit/review tasks require documented evidence with "
            "reviewer sign-off. Both document and reviewer fields "
            "are essential."
        ),
    },

    "default": {
        "keywords": [],
        "priority_evidence": ["api_response", "document_id"],
        "weights": {
            "api_response": 0.40,
            "manual_status": 0.15,
            "document": 0.25,
            "screenshot": 0.05,
            "reviewer": 0.15,
        },
        "min_confidence": 70,
        "severity_base": "MEDIUM",
        "description": (
            "Default profile for unrecognised task types. "
            "Uses balanced evidence weighting."
        ),
    },
}


# -------------------------------------------------------
# Task Classifier
# -------------------------------------------------------

def classify_task(task_description: str) -> str:
    """
    Classify a task description into a category by
    matching keywords from the profile registry.

    Parameters
    ----------
    task_description : str
        The human-readable task description.
        e.g., "Enable MFA for all admin accounts"

    Returns
    -------
    str
        The matched category key (e.g., "mfa", "firewall").
        Returns "default" if no keywords match.
    """
    if not task_description:
        return "default"

    text = task_description.lower()

    # Check each profile's keywords (skip "default")
    best_match = "default"
    best_count = 0

    for category, profile in TASK_PROFILES.items():
        if category == "default":
            continue

        # Count how many keywords from this category appear
        match_count = sum(
            1 for keyword in profile["keywords"]
            if keyword in text
        )

        if match_count > best_count:
            best_count = match_count
            best_match = category

    return best_match


def get_profile(category: str) -> dict:
    """
    Get the validation profile for a task category.

    Parameters
    ----------
    category : str
        Task category from classify_task().

    Returns
    -------
    dict
        The full profile dict with weights, thresholds, etc.
    """
    return TASK_PROFILES.get(category, TASK_PROFILES["default"])


# -------------------------------------------------------
# Context-Aware Evidence Scorer
# -------------------------------------------------------

def score_evidence(evidence: dict, category: str) -> dict:
    """
    Score the provided evidence using context-aware weights.

    Instead of treating all evidence equally, this function
    applies weights specific to the task category.

    Parameters
    ----------
    evidence : dict
        The evidence key-value pairs.
    category : str
        Task category from classify_task().

    Returns
    -------
    dict with:
        weighted_score  — 0.0 to 1.0 (how well-evidenced)
        missing_critical — list of critical evidence fields
                           that are missing
        evidence_quality — "strong" | "moderate" | "weak"
        details         — per-field breakdown
    """
    profile = get_profile(category)
    weights = profile["weights"]

    total_weight = 0.0
    scored_weight = 0.0
    missing_critical = []
    field_details = []

    # Map evidence keys to weight categories
    evidence_mapping = {
        "api_response": "api_response",
        "manual_status": "manual_status",
        "document_id": "document",
        "screenshot_uploaded": "screenshot",
        "reviewer": "reviewer",
    }

    for evidence_key, weight_key in evidence_mapping.items():
        weight = weights.get(weight_key, 0)
        total_weight += weight

        value = evidence.get(evidence_key)
        has_value = (
            value is not None
            and value != ""
            and value != "N/A"
        )

        if has_value:
            scored_weight += weight
            field_details.append({
                "field": evidence_key,
                "present": True,
                "weight": weight,
                "contribution": weight,
            })
        else:
            field_details.append({
                "field": evidence_key,
                "present": False,
                "weight": weight,
                "contribution": 0,
            })
            # Track missing critical evidence
            if weight_key in [
                weights_key
                for weights_key in profile.get("priority_evidence", [])
            ] or weight >= 0.3:
                missing_critical.append(evidence_key)

    # Calculate the weighted score
    weighted_score = (
        scored_weight / total_weight if total_weight > 0 else 0
    )

    # Determine evidence quality
    if weighted_score >= 0.7:
        quality = "strong"
    elif weighted_score >= 0.4:
        quality = "moderate"
    else:
        quality = "weak"

    return {
        "weighted_score": round(weighted_score, 3),
        "missing_critical": missing_critical,
        "evidence_quality": quality,
        "category": category,
        "profile_description": profile["description"],
        "field_details": field_details,
    }
