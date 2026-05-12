# 🏦 Auto-Auditor Validator Agent

> An **Agentic AI micro-service** that independently verifies whether banking compliance tasks were actually completed — instead of trusting manual status updates.

---

## 📁 Project Structure

```
AUTO_VALIDATOR_AGENT/
├── main.py                       ← FastAPI app & API routes
├── requirements.txt              ← Python dependencies
├── README.md                     ← You are here!
├── data/
│   └── compliance_tasks.json     ← Mock database (6 sample tasks)
└── validator/
    ├── __init__.py               ← Makes this a Python package
    ├── schemas.py                ← Pydantic models (data shapes)
    └── engine.py                 ← Core validation logic
```

---

## 🚀 How to Run Locally

### 1. Prerequisites

- **Python 3.10+** installed ([download](https://www.python.org/downloads/))
- A terminal (Command Prompt, PowerShell, or VS Code terminal)

### 2. Install Dependencies

```bash
# Navigate to the project folder
cd AUTO_VALIDATOR_AGENT

# (Optional) Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac / Linux

# Install packages
pip install -r requirements.txt
```

### 3. Start the Server

```bash
uvicorn main:app --reload
```

You should see output like:

```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

### 4. Explore the API

Open your browser and visit:

| URL | What it does |
|---|---|
| http://127.0.0.1:8000/ | Health check — confirms the server is running |
| http://127.0.0.1:8000/docs | **Swagger UI** — interactive API docs (try it!) |
| http://127.0.0.1:8000/tasks | List all compliance tasks |
| http://127.0.0.1:8000/tasks/TASK-001 | Get a single task by ID |
| http://127.0.0.1:8000/validate/TASK-001 | Validate one task |
| http://127.0.0.1:8000/validate/all | Validate **all** tasks (audit report) |

---

## 🔍 How the Validator Works

The engine checks every task against three simple rules:

| # | Condition | Verdict |
|---|---|---|
| 1 | Status = `completed` **and** all evidence fields present | ✅ **PASS** |
| 2 | Status = `completed` **but** evidence is missing | ❌ **FAIL** |
| 3 | Status ≠ `completed` | 🔍 **NEEDS_REVIEW** |

### Expected Results for Sample Data

| Task ID | Title | Verdict |
|---|---|---|
| TASK-001 | KYC Document Verification | ✅ PASS |
| TASK-002 | AML Transaction Review | ❌ FAIL |
| TASK-003 | Internal Audit of Loan Disbursement | 🔍 NEEDS_REVIEW |
| TASK-004 | Data Privacy Impact Assessment | ❌ FAIL |
| TASK-005 | Regulatory Capital Adequacy Reporting | 🔍 NEEDS_REVIEW |
| TASK-006 | Customer Complaint Resolution Audit | ✅ PASS |

---

## 🛠️ Tech Stack

- **Python 3.10+**
- **FastAPI** — modern, high-performance web framework
- **Pydantic** — data validation via type hints
- **Uvicorn** — lightning-fast ASGI server
