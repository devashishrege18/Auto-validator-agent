# -------------------------------------------------------
# validator/schemas.py
# -------------------------------------------------------
# Pydantic models that define the *shape* of data flowing
# through the application.
#
# Why Pydantic?
#   - Automatic data validation (wrong types are caught)
#   - Self-documenting (shows up in Swagger docs)
#   - Easy JSON serialisation
# -------------------------------------------------------

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ---------- Incoming data models ----------

class Evidence(BaseModel):
    """
    Evidence attached to a compliance task.
    If a field is None / null it means that piece of
    evidence has NOT been provided yet.
    """
    document_id: Optional[str] = None   # e.g. "DOC-8831"
    submitted_at: Optional[str] = None  # ISO-8601 timestamp
    reviewer: Optional[str] = None      # Name of the reviewer


class ComplianceTask(BaseModel):
    """
    Represents a single compliance task from the mock
    database. This is what the JSON file stores.
    """
    task_id: str                        # Unique ID, e.g. "TASK-001"
    title: str                          # Human-readable name
    department: str                     # Owning department
    assigned_to: str                    # Person responsible
    status: str                         # "completed" | "in_progress" | "pending"
    evidence: Evidence                  # Supporting proof (may be partial)


# ---------- Outgoing data models ----------

class ValidationResult(BaseModel):
    """
    The verdict the validator engine returns after
    checking a task.

    verdict can be:
      PASS         → task genuinely completed with full evidence
      FAIL         → status says completed but evidence is missing
      NEEDS_REVIEW → task is not yet marked completed
    """
    task_id: str
    title: str
    verdict: str                        # "PASS" | "FAIL" | "NEEDS_REVIEW"
    reasons: List[str]                  # Human-readable explanation(s)
    validated_at: str                   # When the check was performed


# ---------- Reasoning Validator models ----------

class ReasoningRequest(BaseModel):
    """
    Input for the POST /reasoning-validate endpoint.

    The Dispatcher Agent (or a human) sends a task
    description + evidence, and the Reasoning Engine
    returns an intelligent verdict.

    Example:
    {
        "task_id": 1,
        "task": "Enable MFA for admin accounts",
        "evidence": {
            "api_response": true,
            "manual_status": "Done",
            "screenshot_uploaded": true
        }
    }
    """
    task_id: int = 1                    # Unique task identifier
    task: str                           # Description of the compliance task
    evidence: dict                      # Key-value pairs of evidence fields


class ReasoningResponse(BaseModel):
    """
    Standardised output from the Reasoning Validator Engine.

    Contains the verdict plus confidence/risk metrics
    and the LLM's reasoning explanation.
    """
    task_id: int
    status: str                         # "VERIFIED" | "NON_COMPLIANT" | "NEEDS_REVIEW"
    confidence_score: int               # 0-100 (how sure are we?)
    risk_score: int                     # 0-100 (how risky is this?)
    reason: str                         # Human-readable explanation
    concerns: List[str] = []            # Specific concerns found
    recommendation: str = ""            # Action item for the audit team
    suspicion_flags: List[str] = []     # Deterministic flags triggered
    llm_used: bool = False              # Was the LLM used for reasoning?
    llm_model: Optional[str] = None     # Which model (e.g., "phi3")
    timestamp: str = ""                 # When the validation was performed

