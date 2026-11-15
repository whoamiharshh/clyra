# ConfidAgent
> The coding agent that knows what it doesn't know

A CLI coding agent for the Geek Room Global AI Hackathon 2026. Solves PS01 (token efficiency) and PS06 (stale-answer detection).

## What It Does

One command fixes a repo:

```bash
python main.py fix "fix security vulnerabilities" --repo ./demo_repo
```

ConfidAgent breaks the task into atomic decisions, scores each for confidence, routes high-confidence work to a cheap model and low-confidence/security work to a powerful model, verifies library freshness via Tavily, then applies patches with diff approval.

Reads only relevant files, verifies dependency versions via Tavily, scores each decision's confidence, routes to cheap or powerful models accordingly, and patches files with your approval.

## How It Saves Tokens (PS01)

- Relevance filter: reads 3 of 15 files in the demo repo
- Batched execution: one LLM call per file, not per decision
- Confidence routing: HIGH-confidence decisions use the cheap model
- Budget hard-stop: never exceeds your set limit

Measured: 66% token savings (9,478 naive → 3,190 actual), $0.0032 per task.
98% token reduction (illustative estimate, not independently verified)
## How It Catches Stale Answers (PS06)

Before the agent writes any code, Tavily verifies every pinned dependency in requirements.txt. In our demo run, it caught flask-limiter 1.5.0 and pymongo 3.12.0 as stale — both break on current Python 3.13.

## Mandatory Integrations

- Bifrost: all model calls routed with automatic provider failover (Groq → Gemini → OpenRouter)
- Tavily: live web verification for dependency versions

## Safety

- Approval gate: reads auto-approve, writes require explicit y/n
- Budget enforcement: stops before exceeding --budget (default $2.00)
- Privacy detection: repos with .confidential file route to local Ollama only
- File backups: every patch creates a .bak before writing

## Measured Results (verified run)

| Metric | Value |
|--------|-------|
| Tokens used | ~3,190 |
| Naive baseline | 9,478 |
| Token savings | ~66% |
| Cost per task | $0.0032 |
| Stale caught | 2 |

Stale dependencies intercepted: `flask-limiter 1.5.0`, `pymongo 3.12.0`.

## How It Works

1. **TaskAnalyzer**: Breaks user intent into atomic decisions, extracts relevant keywords, computes baseline token metrics.
2. **ConfidenceScorer**: Evaluates decisions (security keywords, volatile packages, stable patterns) assigning confidence 0.10–0.95.
3. **Tavily Freshness Check**: Extracts library version pins and verifies claims via parallel Tavily web searches to detect stale packages.
4. **BudgetGate**: Projects task cost per model tier; halts if budget is insufficient.
5. **Batched LLM Execution**: Groups decisions by target file into one structured prompt via Bifrost/Groq or local Ollama.
6. **Approval & File Patcher**: Diff preview per file, `.bak` backup, then applies the verified patch.

## Key Features

- **Token efficiency**: AST-based relevance filtering sends only target functions to context — in a 15-file repo, only the 3 relevant files reach the LLM (~66% token savings vs naive full-context).
- **Confidence-aware routing**: Cheap model (`openai/gpt-oss-20b`) for high-confidence decisions; powerful model (`openai/gpt-oss-120b`) for low-confidence/security decisions.
- **Stale-answer detection**: Live Tavily verification catches deprecated pins before code generation.
- **Local/confidential mode**: `--confidential` routes everything to Ollama with zero cloud calls; `enforce_local()` blocks cloud tiers when `.confidential` exists, the repo name matches private/confidential/secret/internal, or `CONFIDENTIAL=true` in `.env`.
- **Resume**: In-progress state persists to `.confidagent_state.json`; rerun skips completed decisions.
- **Dashboard**: `streamlit run dashboard.py` for read-only run inspection.

## Demo

![Banner](screenshots/01-banner.png)
![Confidence](screenshots/02-confidence.png)
![Stale Detection](screenshots/03-tavily.png)
![Report](screenshots/05-report.png)

## Quick Start

```powershell
cd confidagent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Fill in GROQ_API_KEY and TAVILY_API_KEY
python main.py fix "fix security vulnerabilities" --repo ./demo_repo
streamlit run dashboard.py
```

## Hackathon

Developed for the **Geek Room Global AI Hackathon 2026**:
- **PS01**: Token Efficiency in Autonomous Coding Agents
- **PS06**: Stale Answer & Deprecated API Detection
