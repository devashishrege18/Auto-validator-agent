# -------------------------------------------------------
# main.py
# -------------------------------------------------------
# Entry point for the Auto-Auditor Validator Agent.
#
# This file:
#   1. Creates the FastAPI application
#   2. Loads mock compliance-task data from a JSON file
#   3. Exposes REST endpoints so users (or other agents)
#      can list tasks and trigger validation checks.
#
# Run the server with:
#   uvicorn main:app --reload
# -------------------------------------------------------

import json
import pathlib
from fastapi import FastAPI, HTTPException

# Our own modules (from the `validator/` package)
from validator.schemas import ComplianceTask, ValidationResult
from validator.engine import validate_task

# -------------------------------------------------------
# 1.  Create the FastAPI app
# -------------------------------------------------------
app = FastAPI(
    title="Auto-Auditor Validator Agent",
    description=(
        "An Agentic AI micro-service that independently verifies "
        "whether banking compliance tasks were actually completed — "
        "instead of trusting manual status updates."
    ),
    version="1.0.0",
)

# -------------------------------------------------------
# 2.  Load mock data once at startup
# -------------------------------------------------------
# pathlib makes file paths work on Windows, Mac, and Linux
DATA_FILE = pathlib.Path(__file__).parent / "data" / "compliance_tasks.json"

def _load_tasks() -> list[ComplianceTask]:
    """
    Read the JSON file and convert each dict into a
    ComplianceTask Pydantic model.
    """
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [ComplianceTask(**item) for item in raw]


# Load once so every request reuses the same list
TASKS: list[ComplianceTask] = _load_tasks()

# -------------------------------------------------------
# 3.  API Endpoints
# -------------------------------------------------------

# --- Health check ---
@app.get("/", tags=["General"])
def health_check():
    """
    Simple health-check endpoint.
    Returns a welcome message confirming the server is up.
    """
    return {
        "message": "Auto-Auditor Validator Agent is running 🚀",
        "docs": "Visit /docs for the interactive API documentation",
    }


# --- List all tasks ---
@app.get("/tasks", response_model=list[ComplianceTask], tags=["Tasks"])
def list_tasks():
    """
    Return every compliance task from the mock database.
    """
    return TASKS


# --- Get a single task by ID ---
@app.get("/tasks/{task_id}", response_model=ComplianceTask, tags=["Tasks"])
def get_task(task_id: str):
    """
    Look up a single compliance task by its task_id.
    Returns 404 if not found.
    """
    for task in TASKS:
        if task.task_id == task_id:
            return task
    # If we reach here, the ID didn't match any task
    raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")


# --- Validate ALL tasks at once ---
# ⚠️ IMPORTANT: This route MUST come before /validate/{task_id}
# because FastAPI matches routes top-to-bottom. If the dynamic
# route came first, "all" would be treated as a task_id.
@app.get("/validate/all", response_model=list[ValidationResult], tags=["Validation"])
def validate_all():
    """
    Bulk-validate every compliance task and return
    a list of verdicts. This is the "audit report" endpoint.
    """
    return [validate_task(task) for task in TASKS]


# --- Validate a single task ---
@app.get("/validate/{task_id}", response_model=ValidationResult, tags=["Validation"])
def validate_single(task_id: str):
    """
    Run the Auto-Auditor engine on one task and return
    a PASS / FAIL / NEEDS_REVIEW verdict.
    """
    # First, find the task
    task = None
    for t in TASKS:
        if t.task_id == task_id:
            task = t
            break

    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found.")

    # Run the validator
    return validate_task(task)
