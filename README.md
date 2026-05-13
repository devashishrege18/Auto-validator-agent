# 🏦 Auto-Auditor Validator Agent

> An **Agentic AI micro-service** that independently verifies whether banking compliance tasks were actually completed — using hybrid deterministic rules + LLM reasoning, instead of trusting manual status updates.

---

## 📁 Project Structure

```
AUTO_VALIDATOR_AGENT/
├── main.py                                ← FastAPI app & all API routes
├── requirements.txt                       ← Python dependencies
├── README.md                              ← You are here!
├── data/
│   ├── compliance_tasks.json              ← Mock database (6 sample tasks)
│   ├── training_data.csv                  ← Generated ML training data
│   ├── compliance_model.pkl               ← Trained ML model (auto-generated)
│   └── audit_log.jsonl                    ← Audit trail (auto-generated)
└── validator/
    ├── __init__.py                        ← Python package marker
    ├── schemas.py                         ← Pydantic models (request/response shapes)
    ├── engine.py                          ← Core rule-based validation logic
    ├── agent.py                           ← Compliance API checker + smart audit
    ├── reasoning_engine.py                ← ⭐ Hybrid LLM + deterministic reasoning
    ├── audit_logger.py                    ← Lightweight audit trail logging
    ├── generate_training_data.py          ← Synthetic data generator (ML pipeline)
    ├── train_model.py                     ← ML model training script
    ├── ml_model.py                        ← ML inference module
    └── llm_reasoner.py                    ← Ollama LLM integration (smart audit)
```

---

## 🚀 How to Run

### 1. Prerequisites

- **Python 3.10+** ([download](https://www.python.org/downloads/))
- **Ollama** for LLM reasoning — [download](https://ollama.com)

### 2. Install & Setup

```bash
cd AUTO_VALIDATOR_AGENT

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac / Linux

# Install packages
pip install -r requirements.txt

# Pull the LLM model (one-time, ~2.3GB)
ollama pull phi3
```

### 3. Train the ML Model (Optional)

```bash
python -m validator.generate_training_data   # Generate 1000 training samples
python -m validator.train_model              # Train Random Forest (86.5% accuracy)
```

### 4. Start the Server

```bash
uvicorn main:app --reload
```

### 5. Open Swagger Docs

Visit **http://127.0.0.1:8000/docs** — all endpoints are interactive!

---

## 🔌 API Endpoints

| Method | Endpoint | What it does |
|---|---|---|
| GET | `/` | Health check |
| GET | `/docs` | Swagger UI (interactive docs) |
| GET | `/tasks` | List all compliance tasks |
| GET | `/tasks/{task_id}` | Get a single task |
| GET | `/validate/{task_id}` | Validate one task (rule-based) |
| GET | `/validate/all` | Validate all tasks |
| GET | `/mfa-status` | Mock MFA API |
| GET | `/firewall-status` | Mock firewall API |
| GET | `/password-policy` | Mock password policy API |
| GET | `/audit` | Rule-based compliance audit |
| GET | `/audit/smart` | ML + LLM powered audit |
| **POST** | **`/reasoning-validate`** | **⭐ Intelligent LLM reasoning validator** |
| GET | `/audit-trail` | View validation audit log |
| GET | `/audit-stats` | Audit trail statistics |

---

## ⭐ Flagship: POST `/reasoning-validate`

The core agentic endpoint — accepts any compliance task + evidence, runs hybrid reasoning, returns a standardised verdict.

### Input

```json
{
    "task_id": 1,
    "task": "Enable MFA for admin accounts",
    "evidence": {
        "api_response": true,
        "manual_status": "Done",
        "screenshot_uploaded": true
    }
}
```

### Output

```json
{
    "task_id": 1,
    "status": "VERIFIED",
    "confidence_score": 98,
    "risk_score": 0,
    "reason": "MFA confirmed through API verification and supporting evidence.",
    "concerns": [],
    "recommendation": "No further action required; continue routine monitoring.",
    "suspicion_flags": [],
    "llm_used": true,
    "llm_model": "phi3",
    "timestamp": "2026-05-13T12:23:05+00:00"
}
```

### How it Works

```
Input (task + evidence)
        │
        ▼
┌─────────────────────────────────┐
│  1. SUSPICION DETECTOR          │  ← Deterministic rules
│     • Missing evidence?         │     (instant, reliable)
│     • Contradictions?           │
│     • Manual-only claims?       │
│     • API negative?             │
└───────────┬─────────────────────┘
            │ suspicion flags
            ▼
┌─────────────────────────────────┐
│  2. RISK & CONFIDENCE SCORING   │  ← Weighted calculation
│     • Risk: 0-100               │
│     • Confidence: 0-100         │
└───────────┬─────────────────────┘
            │ scores + context
            ▼
┌─────────────────────────────────┐
│  3. LLM REASONING (Ollama/phi3) │  ← Intelligent analysis
│     • Evidence sufficiency?     │     (nuanced, contextual)
│     • Is task truly compliant?  │
│     • Anything suspicious?      │
└───────────┬─────────────────────┘
            │ structured verdict
            ▼
┌─────────────────────────────────┐
│  4. AUDIT LOGGER                │  ← Compliance traceability
│     • Appends to audit_log.jsonl│
└───────────┬─────────────────────┘
            │
            ▼
    Standardised Response
```

### Suspicion Detection Patterns

| Flag | Trigger | Risk Weight |
|---|---|---|
| `NO_EVIDENCE` | Empty evidence dict | 30 |
| `CONTRADICTORY_EVIDENCE` | API says False, manual says "Done" | 25 |
| `API_NEGATIVE` | API explicitly returned False | 25 |
| `MANUAL_WITHOUT_API` | Manual claim with no API check | 20 |
| `SCREENSHOT_ONLY` | Only screenshot, no corroboration | 15 |
| `MOSTLY_EMPTY` | >50% of fields are null/empty | 15 |
| `API_ONLY_NO_SUPPORT` | API True but no supporting docs | 10 |

---

## 🏗️ Architecture

Modular and integration-ready for:

- **Dispatcher Agent** → sends tasks to `/reasoning-validate`
- **Spectre-Sentinel Watchdog** → monitors `/audit-stats` and risk scores
- **Frontend Dashboard** → displays verdicts from `/audit-trail`

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| API Framework | FastAPI |
| Data Validation | Pydantic |
| Server | Uvicorn |
| Local LLM | Ollama (phi3) |
| ML Model | scikit-learn (Random Forest) |
| Data Processing | pandas |
| Audit Trail | JSON-lines file |
