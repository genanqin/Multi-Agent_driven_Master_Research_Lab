# Architecture

## Product Shape

大师投研室 is a local A-share research assistant built around deterministic market signals, six style-separated master agents, MAAD debate, and a portfolio manager that converts opinions into executable A-share lots.

The app has two surfaces:

- FastAPI backend in `app/`
- Static HTML/CSS/JS frontend in `app/static/`

Operational helpers live at the project root:

- `start_macos.command` starts the app on macOS.
- `start_windows.bat` starts the app on Windows.
- `Quant_Multiagent_Math_Principles.ipynb` documents the mathematical mechanisms behind each layer.
- `.env.example` provides safe public configuration placeholders; real `.env` files are ignored.

## Runtime Flow

1. `app/main.py` receives `POST /api/analyze`.
2. `QuantPipeline` resolves symbols and loads market data.
3. `DataProvider` tries AKShare first, then falls back to deterministic mock data.
4. Signal agents generate technical, fundamental, and news/sentiment signals.
5. `MasterAgentOrchestrator` builds a shared factor vector for every symbol.
6. Each master agent forms an opinion:
   - Rules produce `baseline_score`, `baseline_action`, and baseline confidence.
   - If `MASTER_DECISION_MODE` is not `rules` and an LLM is configured, the LLM returns strict JSON for `action`, `score`, `confidence`, and `reason`.
   - Guardrails clamp LLM scores around the rule anchor and block unsafe buy/sell flips.
   - If the LLM is unavailable or malformed, the rules result is used.
7. `MAADDebate` selects high-conflict masters and revises score/confidence through debate turns. Each single stock can send at most three masters into the debate.
8. `InvestmentManagerAgent` aggregates revised opinions, applies risk/data-quality penalties, max single-name weight, and 100-share lot constraints.
9. The API returns factors, opinions, debate transcript, final portfolio, cash, and summary.

## Agent Boundaries

Master agents share the same visible factor set, but each has:

- `system_prompt`: persona and behavior boundary
- `factor_preference`: preferred evidence weighting for explanation and conviction
- `style_prior`: vector used by debate to measure style distance
- scorer function: deterministic baseline that anchors the LLM decision

LLM system prompts explicitly isolate each master: one response may represent only one master and may not act as judge, manager, consensus engine, or another master.

## Configuration

Environment is loaded from `.env` through `pydantic-settings`.

- `LLM_PROVIDER`: `mock` disables real LLM calls.
- `LLM_API_KEY`: required for real LLM calls.
- `LLM_BASE_URL`: OpenAI-compatible `/chat/completions` base URL.
- `LLM_MODEL`: model name.
- `MASTER_DECISION_MODE`: `hybrid` by default, `rules` for deterministic master decisions.
- `MASTER_LLM_MAX_SCORE_DELTA`: max LLM score drift from rule baseline, default `0.18`.
- `ENABLE_AKSHARE`: enables real data fetching when available.

## Failure Strategy

The project is designed to keep running locally:

- Data failures fall back to deterministic mock market data.
- LLM failures are recorded for the current request and fall back to deterministic rule decisions or template text.
- LLM malformed JSON falls back to deterministic rule decisions.
- Debate and portfolio allocation work with either LLM or rule-generated opinions.
- Final summaries include a short fallback notice if external LLM calls failed during that analysis.

## Public Release Contents

The public repository includes:

- source code under `app/`
- static assets under `app/static/`
- safe configuration example `.env.example`
- MIT `LICENSE`
- `tests/` smoke tests
- docs under `docs/`
- launchers for macOS and Windows

It must not include:

- `.env`
- `.venv`
- `__pycache__`
- `.pytest_cache`
- local screenshots or unrelated desktop files
- real API keys
