# Known Issues

## Data

- AKShare availability can vary by network, upstream endpoint, and market calendar. The app falls back to deterministic mock data when real data fails.
- Mock data is suitable for demos and pipeline testing only. It is not market evidence.
- News and research report samples are limited by available AKShare endpoints and may not cover all relevant disclosures.

## LLM Decisions

- Default local config uses `LLM_PROVIDER=mock`, so LLM master decisions are inactive until a real provider is configured.
- The LLM decision interface expects strict JSON. Malformed output falls back to the baseline rule decision.
- Guardrails reduce extreme LLM deviations, but they do not make outputs investment advice.
- LLM reason text is constrained by prompt and truncation, but deeper factual contradiction detection is not yet implemented.
- Real LLM calls are currently serial. One-symbol DeepSeek smoke testing can take roughly minutes because master opinions, debate turns, and final summary each call the model.
- The user-facing LLM fallback notice reports the number of recent errors, but does not yet show structured per-stage diagnostics.

## Portfolio Logic

- Allocation uses a simple max single-name weight and 100-share lot rule.
- There is no sector exposure model, liquidity model, tax/slippage model, or explicit cash target yet.
- Final scores are heuristic and not calibrated by backtesting.

## Engineering

- Repository metadata and CI setup may vary depending on how the project is published.
- The automated test suite is intentionally small and currently covers only smoke-level backend behavior.
- `start_macos.command` can install dependencies, which requires network access if `.venv` is incomplete.
- `start_windows.bat` has been added but still needs smoke testing on an actual Windows machine.
- Frontend versions exist under `app/static/v1` and `app/static/v2`, but the root `app/static/index.html` is the served UI.
- Browser-level visual regression tests are not automated yet; frontend layout changes are checked manually through local rendering.
- Included investor portrait assets are illustrative UI assets. Public redistribution should review image rights and replace assets if necessary.
- Keep local-only files such as `.env`, `.venv`, generated caches, screenshots, and private development notes out of published commits.
