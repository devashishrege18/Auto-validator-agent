# -------------------------------------------------------
# validator/engine.py
# -------------------------------------------------------
# The *brain* of the Auto-Auditor Validator Agent.
#
# Instead of blindly trusting a task's self-reported
# "status" field, this module cross-checks the evidence
# and returns an independent verdict.
#
# Validation Rules
# ────────────────
# 1. Status is "completed" AND all 3 evidence fields
#    are present                          → PASS  ✅
# 2. Status is "completed" BUT one or more evidence
#    fields are missing                   → FAIL  ❌
# 3. Status is anything other than
#    "completed"                          → NEEDS_REVIEW  🔍
# -------------------------------------------------------

from datetime import datetime, timezone
from validator.schemas import ComplianceTask, ValidationResult


def validate_task(task: ComplianceTask) -> ValidationResult:
    """
    Run the validation rules on a single ComplianceTask
    and return a ValidationResult with the verdict.

    Parameters
    ----------
    task : ComplianceTask
        The task to validate (loaded from mock DB).

    Returns
    -------
    ValidationResult
        Contains verdict, human-readable reasons, and a
        timestamp of when the validation was performed.
    """

    # We'll collect reasons as we go
    reasons: list[str] = []

    # ------- Rule 3: Task not marked completed -------
    if task.status != "completed":
        reasons.append(
            f"Task status is '{task.status}' — not yet marked as completed."
        )
        return ValidationResult(
            task_id=task.task_id,
            title=task.title,
            verdict="NEEDS_REVIEW",
            reasons=reasons,
            validated_at=_now(),
        )

    # ------- Rules 1 & 2: Check evidence completeness -------
    missing_fields: list[str] = []

    if not task.evidence.document_id:
        missing_fields.append("document_id")
    if not task.evidence.submitted_at:
        missing_fields.append("submitted_at")
    if not task.evidence.reviewer:
        missing_fields.append("reviewer")

    if missing_fields:
        # Rule 2 — status says "completed" but evidence is incomplete
        reasons.append(
            "Task is marked 'completed' but the following evidence "
            f"is missing: {', '.join(missing_fields)}."
        )
        verdict = "FAIL"
    else:
        # Rule 1 — everything checks out
        reasons.append(
            "All evidence fields are present and task status is 'completed'. "
            "Validation passed."
        )
        verdict = "PASS"

    return ValidationResult(
        task_id=task.task_id,
        title=task.title,
        verdict=verdict,
        reasons=reasons,
        validated_at=_now(),
    )


# -------------------------------------------------------
# Helper
# -------------------------------------------------------

def _now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
