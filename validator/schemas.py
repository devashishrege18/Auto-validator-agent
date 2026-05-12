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
