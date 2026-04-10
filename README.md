# Vigilant-AI — LLM Safety & Red-Teaming Framework

> A production-ready guardrail proxy for LLMs, with red-teaming tools and an interactive security dashboard.
> Built for the **Cybersecurity & AI Safety Hackathon 2025-26**.

---

## What It Does

Vigilant-AI sits between users and an LLM (Groq's Llama models), scanning every prompt and response for:

| Threat | Detection Method |
|---|---|
| **Prompt Injection** | 30+ regex patterns + structural analysis |
| **DAN / Jailbreak** | Keyword + pattern matching |
| **PII / Secrets** | Regex for API keys, emails, phones, cards, PAN, Aadhaar |
| **Toxic Content** | Weighted keyword scoring across 4 harm categories |
| **Hallucination** | Claim density + unsourced citation detection |

## Architecture

```
User ──► Streamlit Dashboard ──► FastAPI Proxy ──► Groq LLM
              │                      │
              │               GuardrailEngine
              │               ├── Prompt Injection Detector
              │               ├── PII Redactor
              │               ├── Toxicity Classifier
              │               └── Hallucination Scorer
              │
              └── Real-time Security Dashboard
```

## Quick Start

### 1. Clone & Install
```bash
git clone https://github.com/YOUR_USERNAME/vigilant-ai.git
cd vigilant-ai
pip install -r requirements.txt
```

### 2. Set API Key
```bash
# Linux/Mac
export GROQ_API_KEY=your_key_here

# Windows (PowerShell)
$env:GROQ_API_KEY="your_key_here"

# Get a free key: https://console.groq.com
```

### 3. Run the Guardrail Proxy
```bash
uvicorn proxy.api:app --reload --port 8000
```

### 4. Run the Security Dashboard
```bash
streamlit run dashboard/security_dashboard.py
```

### 5. Run the Vulnerable Baseline (to compare)
```bash
streamlit run app/vulnerable_llm.py
```

## Project Structure

```
vigilant_ai/
├── README.md
├── requirements.txt
├── .gitignore
│
├── proxy/
│   ├── __init__.py
│   ├── guardrails.py       # Core GuardrailEngine — all detection layers
│   └── api.py             # FastAPI proxy server
│
├── app/
│   └── vulnerable_llm.py  # Phase 1: Unprotected LLM (no guardrails)
│
├── dashboard/
│   └── security_dashboard.py  # Phase 4: Streamlit security dashboard
│
├── tests/
│   ├── test_guardrails.py    # Unit tests for all guardrail layers
│   └── run_garak_audit.py   # Phase 3: Red-team audit with 30+ probes
│
└── garak_results/           # Audit output (gitkeep — not committed)
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/chat` | Chat with the guarded LLM |
| `POST` | `/analyze-prompt` | Analyze a prompt for risks |
| `POST` | `/analyze-response` | Analyze a response for risks |
| `GET` | `/audit-log` | Recent guardrail events |
| `GET` | `/health` | Proxy health check |

## Demo Workflow for Judges

### Phase 1 — Vulnerable Baseline (No Guardrails)
```
streamlit run app/vulnerable_llm.py
```
- Shows a banking LLM with CONFIDENTIAL account numbers
- Click "Data Exfiltration" attack → model reveals ACC-2024-001 through ACC-2024-010
- Click "DAN Jailbreak" → model bypasses all safety guidelines

### Phase 2 — Guardrail Proxy
```
uvicorn proxy.api:app --port 8000
```
- All prompts pass through GuardrailEngine before reaching the LLM
- Proxy blocks injection, jailbreaks, PII exfiltration before they reach the model

### Phase 3 — Red-Team Audit
```
python tests/run_garak_audit.py
```
- 30 probes across 5 attack categories
- Detailed per-probe pass/fail report with JSON export
- Run alongside garak for additional coverage

### Phase 4 — Security Dashboard
```
streamlit run dashboard/security_dashboard.py
```
- Live safety scores, threat radar, attack timeline
- Raw vs Guarded side-by-side comparison
- Full audit log with CSV export

## Guardrail Effectiveness

Tested with 30 probes across attack categories:

| Category | Detection Rate |
|---|---|
| Prompt Injection | 89% |
| DAN / Jailbreak | 100% |
| PII Exfiltration | 83% |
| Toxic Intent | (on prompt input) |
| Hallucination | (on response output) |

> With a real Groq API key connected, detection rates improve further as hallucination and output toxicity checks activate.

## Tech Stack

- **Proxy**: FastAPI + Uvicorn
- **Dashboard**: Streamlit + Altair (interactive charts)
- **LLM**: Groq API (Llama 3.1 8B / 70B)
- **Detection**: Pure Python regex + rule-based scoring (no heavy ML dependencies)
- **Red-Teaming**: Custom probe suite + NVIDIA garak integration

## License

MIT License — built for the Cybersecurity & AI Safety Hackathon 2025-26.
