# AI Investment Research Workbench

Local-first AI investment research system for A-share, Hong Kong, and US equities.

## Architecture

- Python FastAPI backend in `src/api`
- LangGraph multi-agent research pipeline in `src/agents/research`
- Provider registry and fallback data layer in `src/data`
- Next.js App Router frontend in `frontend`
- Legacy Streamlit dashboard retained in `src/dashboard`

## Quick Start

```powershell
python -m pip install -e ".[dev]"
python scripts/init_db.py --reset
python scripts/run_api.py
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Validation

```powershell
python -m compileall -q src scripts config
pytest -q
cd frontend
npm run lint
npm run build
```

## LLM Providers

Copy `.env.example` to `.env` and configure any OpenAI-compatible provider:

- DeepSeek
- OpenAI
- Qwen / DashScope
- SiliconFlow
- OpenRouter
- Volcengine Ark
- Ollama local models

The system can run deterministic research without an LLM key; enabling `use_llm` polishes the thesis when a provider is configured.
