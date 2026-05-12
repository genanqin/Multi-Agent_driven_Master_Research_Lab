# Roadmap

## Near Term

- Keep the public repository free of local `.env`, `.venv`, generated caches, screenshots, and private development state.
- Smoke-test `start_windows.bat` on a real Windows machine.
- Add GitHub Actions CI for `python -m compileall app`, `node --check app/static/app.js`, and `pytest`.
- Add automated tests for `MasterAgentOrchestrator` covering rules mode, valid LLM JSON, malformed LLM output, and guardrail corrections.
- Expand automated tests for MAAD participant selection beyond the current smoke cap check.
- Add a visible frontend indicator for data source and decision source.
- Add request-level timing and richer LLM failure diagnostics to API responses or server logs.
- Add a documented asset-replacement workflow for users who want to swap portrait images before public deployment.

## Product Improvements

- Stream analysis progress to the frontend so users can see data fetch, agent opinion, debate, and allocation stages.
- Add per-master decision audit fields, including baseline score, LLM raw score, guarded score, and guardrail reason.
- Add richer portfolio constraints: cash target, sector caps, max number of holdings, and minimum conviction.
- Add exportable research report output.
- Add notebook examples that run a small mock analysis and visualize intermediate factor values.

## Research Improvements

- Calibrate scoring thresholds on historical A-share samples.
- Add factor backtesting for the baseline scorer and hybrid LLM deviations.
- Add contradiction checks between LLM reason text and structured action/score.
- Improve news event extraction with structured event tags.

## Reliability Improvements

- Add cache for AKShare responses.
- Add timeout and retry policy per data source.
- Parallelize independent LLM calls for per-master decisions and debate generation, with a concurrency limit.
- Add snapshot tests for mock-data deterministic outputs.
- Add a smoke API call to CI once external network-dependent data paths are isolated from default tests.
