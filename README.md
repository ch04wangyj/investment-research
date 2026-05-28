# AI Investment Research Workbench

Local-first AI investment research system for A-share, Hong Kong, and US equities.

## Architecture

- Python FastAPI backend in `src/api`
- LangGraph multi-agent research pipeline in `src/agents/research`
- Provider registry and fallback data layer in `src/data`
- Next.js App Router frontend in `frontend`

The research pipeline uses TradingAgents-style role separation without copying
third-party code: information collection/summarization, fundamentals,
technical analysis, sentiment, bull/bear debate, trading strategy, and final
research director synthesis.

## Quick Start

One-click local startup:

```powershell
.\start_workbench.bat
```

Manual startup:

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

The backend defaults to `http://127.0.0.1:8000`. If that port is occupied, set
`API_PORT` in `.env` and `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`.

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

## Main API Routes

- `GET /api/market/overview` - indices, watchlist quotes, sector groups, rating groups
- `GET /api/risk/alerts` - portfolio-level risk alerts
- `GET /api/risk/alerts/{symbol}` - symbol-level drawdown, policy, cycle, and earnings risk alerts
- `POST /api/research/{symbol}` - run the multi-agent research pipeline
- `POST /api/assistant/{symbol}` - generate assistant messages from information and strategy roles
