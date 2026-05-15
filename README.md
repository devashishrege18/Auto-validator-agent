# 🏦 Auto-Auditor Validator Agent

> An **Agentic AI micro-service** (v2.0) that independently verifies whether banking compliance tasks were actually completed — using a hybrid pipeline of deterministic rules, context-aware ML risk scoring, and local LLM reasoning, instead of trusting manual status updates.

---

## ⚡ Key Features

| Feature | Description |
|---|---|
| **Context-Aware Validation** | Different task types (MFA, firewall, training) use different validation strategies with weighted evidence scoring |
| **12 Suspicion Patterns** | Detects contradictions, manual bypasses, timestamp anomalies, duplicate evidence, and more |
| **Watchdog Alert System** | Generates CRITICAL/WARNING/INFO alerts for Spectre-Sentinel integration |
| **Explainable Reasoning Chain** | Step-by-step trace of every decision the engine made — fully auditable |
| **Standardized API Envelope** | Every response wrapped in `{success, agent, version, data, meta}` for multi-agent interop |
| **Multi-Model LLM Fallback** | Tries phi3 → llama3 → mistral with response caching for speed |
| **ML Risk Classification** | Custom-trained Random Forest predicts risk level (LOW/MEDIUM/HIGH/CRITICAL) and compliance score (0-100) |
| **Multi-Agent Demo Script** | 7-scenario demo simulating Dispatcher → Validator → Watchdog flow |
| **Comprehensive Test Suite** | 120 unit + integration tests with 100% pass rate |

---

## 📁 Project Structure

```
AUTO_VALIDATOR_AGENT/
├── main.py                                ← FastAPI app & all API routes
├── demo.py                                ← 7-scenario hackathon demo script
├── requirements.txt                       ← Python dependencies
├── README.md                              ← You are here!
├── data/
│   ├── compliance_tasks.json              ← Mock database (6 sample tasks)
│   ├── training_data.csv                  ← Generated ML training data
│   ├── compliance_model.pkl               ← Trained ML model (auto-generated)
│   └── audit_log.jsonl                    ← Audit trail (auto-generated)
├── validator/
│   ├── __init__.py                        ← Python package marker
│   ├── schemas.py                         ← Pydantic models (request/response shapes)
│   ├── engine.py                          ← Core rule-based validation logic
│   ├── agent.py                           ← Compliance API checker + smart audit
│   ├── reasoning_engine.py                ← ⭐ Hybrid reasoning with reasoning chain
│   ├── task_profiles.py                   ← Context-aware task classification
│   ├── watchdog.py                        ← Spectre-Sentinel alert system
│   ├── response.py                        ← Standardized API response envelope
│   ├── audit_logger.py                    ← Audit trail logging with severity
│   ├── generate_training_data.py          ← Synthetic data generator (ML pipeline)
│   ├── train_model.py                     ← ML model training script
│   ├── ml_model.py                        ← ML inference module
│   └── llm_reasoner.py                    ← Ollama LLM integration (smart audit)
└── tests/
    ├── test_schemas.py                    ← Pydantic model tests (13)
    ├── test_engine.py                     ← Validation engine tests (13)
    ├── test_reasoning.py                  ← Reasoning engine tests (22)
    ├── test_ml_pipeline.py                ← ML pipeline tests (17)
    ├── test_api.py                        ← FastAPI endpoint tests (26)
    ├── test_task_profiles.py              ← Task classification tests (13)
    └── test_watchdog.py                   ← Watchdog alert tests (9)
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
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac / Linux

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

### 5. Run Tests

```bash
python -m pytest tests/ -v
```

### 6. Open Swagger Docs

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
| **POST** | **`/reasoning-validate`** | **⭐ Intelligent reasoning validator** |
| GET | `/audit-trail` | View validation audit log |
| GET | `/audit-stats` | Audit trail statistics |
| GET | `/watchdog/alerts` | 🔴 Watchdog alerts (Spectre-Sentinel) |
| GET | `/watchdog/status` | 🟢🟡🔴 Compliance health status |

---

## 🧠 Intelligence Architecture

```
┌─────────────────────────────────────────────────┐
│              POST /reasoning-validate            │
└──────────────────────┬──────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │  1. CLASSIFY TASK       │  ← task_profiles.py
          │     (MFA/firewall/etc.) │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  2. SCORE EVIDENCE      │  ← Context-aware weights
          │     (strong/moderate/   │
          │      weak)              │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  3. DETECT SUSPICIONS   │  ← 12 patterns
          │     (contradictions,    │
          │      timestamps, etc.)  │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  4. CALCULATE SCORES    │
          │     confidence: 0-100   │
          │     risk:       0-100   │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  5. LLM REASONING       │  ← phi3 → llama3 → mistral
          │     (or deterministic   │     + response caching
          │      fallback)          │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  6. WATCHDOG ALERT      │  ← watchdog.py
          │     CRITICAL/WARNING/   │     → Spectre-Sentinel
          │     INFO/CLEAR          │
          └────────────┬────────────┘
                       │
          ┌────────────▼────────────┐
          │  7. RETURN RESULT       │
          │     + reasoning_chain   │
          │     + severity level    │
          └─────────────────────────┘
```

---

## 🔍 Suspicion Detection Patterns

| # | Pattern | What It Catches | Weight |
|---|---|---|---|
| 1 | `NO_EVIDENCE` | Empty evidence for a completed task | 30 |
| 2 | `MANUAL_WITHOUT_API` | Manual "Done" without API verification | 20 |
| 3 | `CONTRADICTORY_EVIDENCE` | API=False but manual="Done" | 25 |
| 4 | `API_ONLY_NO_SUPPORT` | API=True but no docs/screenshot/reviewer | 10 |
| 5 | `SCREENSHOT_ONLY` | Only screenshot, no API or reviewer | 15 |
| 6 | `MOSTLY_EMPTY` | >50% evidence fields are null | 15 |
| 7 | `API_NEGATIVE` | API explicitly returned False | 25 |
| 8 | `TIMESTAMP_ANOMALY` | Future timestamps or unusual hours | 10-20 |
| 9 | `API_UNAVAILABLE_BYPASS` | Completed during API outage window | 25 |
| 10 | `CROSS_FIELD_MISMATCH` | Reviewer but no doc, or doc but no reviewer | 10 |
| 11 | `SUSPICIOUSLY_FAST` | Task completed in under 5 minutes | 15 |
| 12 | `DUPLICATE_EVIDENCE` | Same document reused across tasks | 15 |

---

## 🤝 Integration Points

This agent is designed to work within a multi-agent banking compliance system:

| System | Integration | Endpoint |
|---|---|---|
| **Dispatcher Agent** | Sends tasks for validation | `POST /reasoning-validate` |
| **Spectre-Sentinel** | Polls for security alerts | `GET /watchdog/alerts`, `/watchdog/status` |
| **Unified Dashboard** | Displays audit results | `GET /audit/smart`, `/audit-trail` |

All responses use a **standardised envelope**:
```json
{
  "success": true,
  "agent": "auto-auditor-validator",
  "version": "2.0.0",
  "timestamp": "2026-05-16T...",
  "data": { "...actual payload..." },
  "meta": { "request_id": "a1b2c3d4", "processing_ms": 42.1 }
}
```

---

## 🎬 Demo

Run the full multi-agent workflow simulation:

```bash
# Terminal 1: Start the server
uvicorn main:app --reload

# Terminal 2: Run the demo
python demo.py
```

The demo runs 7 banking scenarios showing: clean passes, contradictions, ghost completions, API outage bypasses, timestamp anomalies, and cross-field mismatches.

---

## 🧪 Test Coverage

```
120 tests across 7 test files:

  test_schemas.py        — 13 tests (Pydantic models)
  test_engine.py         — 13 tests (rule-based validation)
  test_reasoning.py      — 22 tests (suspicion detection, scoring, verdicts)
  test_ml_pipeline.py    — 17 tests (data generation, feature extraction)
  test_api.py            — 33 tests (endpoints, envelope, watchdog routes)
  test_task_profiles.py  — 13 tests (task classification, evidence scoring)
  test_watchdog.py       —  9 tests (alert evaluation, health status)
```

Run: `python -m pytest tests/ -v`

