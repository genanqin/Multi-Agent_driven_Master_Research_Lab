# 大师投研室

> 一个面向 A 股研究的本地多 Agent 投资辩论系统：用技术、财务和新闻信号驱动 6 位大师风格 Agent，经 MAAD 辩论后由投资经理 Agent 输出组合建议。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![Frontend](https://img.shields.io/badge/Frontend-HTML%2FCSS%2FJS-orange)
![Status](https://img.shields.io/badge/status-local%20prototype-lightgrey)

## Overview

大师投研室是一个可本地运行的 A 股投研原型项目。用户输入最多 6 支股票和资金池后，系统会抓取或模拟行情、财务、研报和新闻数据，生成结构化因子，让 6 位不同投资风格的大师 Agent 独立判断，再通过 MAAD 辩论机制修正观点，最后由投资经理 Agent 生成仓位、股数、现金和解释文本。

项目默认可以在没有大模型 API 的情况下离线演示；配置 DeepSeek 或兼容 OpenAI Chat Completions 的模型后，大师观点、辩论文本和投资经理总结会进入 hybrid LLM 模式。

## Features

- 支持最多 6 支 A 股股票代码或中文名称输入。
- 使用 AKShare 获取行情、近 4 个季度财务指标、近半年研报和近 3 个月新闻。
- AKShare 或网络不可用时自动回退确定性 mock 数据，保证本地可演示。
- 内置 6 位大师风格 Agent：
  - Buffett
  - Graham
  - Lynch
  - Soros
  - Dalio
  - Templeton
- 大师 Agent 使用独立 system prompt、style prior、规则基线评分和风格偏好因子。
- 支持 LLM 决策 + 规则护栏：
  - LLM 可参与买入、持有、卖出判断。
  - 规则分数作为锚点和风控阈值。
  - LLM 异常、JSON 不合法或越界时自动回退规则结果。
- MAAD 辩论机制：
  - 根据风格距离、分数偏离、动作冲突和信心度选择参与者。
  - 每只股票最多 3 位大师参与辩论。
  - 每位参与者最多发言 3 次。
  - 内部计算 attack strength、defense strength、confidence delta 和 factor delta。
- 投资经理 Agent：
  - 使用辩论修正后的分数和信心度。
  - 叠加波动率、分歧度、数据质量惩罚。
  - 遵守单股最大 60% 仓位和 A 股 100 股一手交易规则。
- 提供 macOS 和 Windows 一键启动脚本。
- 提供 Jupyter 原理文档，解释项目各层数理机制。

## Screens and Flow

```text
用户输入股票和资金
        |
        v
数据层：行情 / 财务 / 研报 / 新闻
        |
        v
信号层：技术 Agent / 财务 Agent / 新闻情绪 Agent
        |
        v
大师层：6 位大师 Agent 独立判断
        |
        v
MAAD 辩论：冲突选择、轮流发言、分数与信心修正
        |
        v
投资经理：风险惩罚、投票、仓位、一手交易约束
        |
        v
最终组合、现金、解释文本
```

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | FastAPI, Uvicorn, Pydantic |
| Data | AKShare, pandas, numpy |
| LLM Adapter | OpenAI-compatible Chat Completions API |
| Frontend | HTML, CSS, JavaScript, Chart.js |
| Runtime | Python virtual environment |

## Requirements

- Python 3.10+
- macOS, Windows, or Linux
- Network access for first-time dependency installation
- Optional: DeepSeek or another OpenAI-compatible model API key

Windows users must install Python first. `start_windows.bat` creates the project virtual environment, but it does not install Python itself.

## Security and API Keys

This repository does not include any real LLM API key. Users should provide their own credentials locally.

1. Copy `.env.example` to `.env`.
2. Keep `LLM_PROVIDER="mock"` for offline deterministic demos, or configure your own provider.
3. Never commit `.env` or any personal API key.

`.gitignore` excludes `.env`, `.venv`, Python caches, local logs, and common editor/system files.

## Quick Start

### macOS

```bash
./start_macos.command
```

You can also double-click `start_macos.command` in Finder.

To specify a port:

```bash
APP_PORT=8010 ./start_macos.command
```

### Windows

```bat
start_windows.bat
```

You can also double-click `start_windows.bat` in File Explorer.

To specify a port:

```bat
set APP_PORT=8010
start_windows.bat
```

### Manual Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## Configuration

Create a `.env` file in the project root when you want to override defaults.

```env
APP_NAME="大师投研室"
ENABLE_AKSHARE=true

LLM_PROVIDER="mock"
LLM_API_KEY=""
LLM_BASE_URL=""
LLM_MODEL="deepseek-v4-pro"

MASTER_DECISION_MODE="hybrid"
MASTER_LLM_MAX_SCORE_DELTA=0.18
```

### LLM Setup

For DeepSeek or another compatible API:

```env
LLM_PROVIDER="deepseek"
LLM_API_KEY="your-api-key"
LLM_BASE_URL="https://api.deepseek.com"
LLM_MODEL="deepseek-v4-pro"
MASTER_DECISION_MODE="hybrid"
MASTER_LLM_MAX_SCORE_DELTA=0.18
```

When `LLM_PROVIDER=mock` or no API key is configured, the system uses deterministic local rules.

If an external LLM request fails, the backend records the error for the current run, falls back to local rules or template text, and appends a short fallback notice to the final summary.

## API

### Health Check

```bash
curl http://127.0.0.1:8000/api/health
```

### Analyze Portfolio

```bash
curl -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbols":["600519","000001","300750"],"capital":1000000}'
```

Request body:

| Field | Type | Description |
| --- | --- | --- |
| `symbols` | `string[]` | 1 to 6 stock codes or Chinese names |
| `capital` | `int` | RMB capital pool, from 10,000 to 10,000,000 |

Response includes:

- resolved request
- price snapshots
- technical signals
- fundamental signals
- news signals
- master opinions
- MAAD debate rounds
- portfolio positions
- cash
- investment manager summary

## Project Structure

```text
.
├── app/
│   ├── agents/
│   │   ├── signals.py      # technical, fundamental, and news signal agents
│   │   ├── masters.py      # master personas, baseline scoring, LLM guardrails
│   │   ├── debate.py       # MAAD debate participant selection and revisions
│   │   └── judge.py        # investment manager and portfolio allocation
│   ├── models/
│   │   └── schemas.py      # Pydantic request and response schemas
│   ├── services/
│   │   ├── data_provider.py
│   │   ├── llm_client.py
│   │   └── pipeline.py
│   ├── static/
│   │   ├── index.html
│   │   ├── styles.css
│   │   └── app.js
│   └── main.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   └── KNOWN_ISSUES.md
├── Quant_Multiagent_Math_Principles.ipynb
├── requirements.txt
├── start_macos.command
└── start_windows.bat
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Known Issues](docs/KNOWN_ISSUES.md)
- [Math Principles Notebook](Quant_Multiagent_Math_Principles.ipynb)

## Development Notes

Run a quick syntax check:

```bash
python -m compileall app
node --check app/static/app.js
```

Run tests:

```bash
pytest
```

Run a local API smoke test with mock data:

```bash
ENABLE_AKSHARE=false LLM_PROVIDER=mock uvicorn app.main:app --reload
```

Then call `/api/analyze` with the curl example above.

## Limitations

- This is a local research prototype, not a production trading system.
- AKShare data availability depends on network and upstream endpoints.
- LLM calls are currently serial and can be slow when a real model is enabled.
- The baseline scoring and risk penalties are heuristic and not calibrated by formal backtesting.
- Windows launcher is provided, but should still be smoke-tested on the target Windows machine.

## Asset Notice

This project includes portrait assets for investor-style educational agents. They are used only as illustrative UI elements to represent investing styles and historical personas. The project is not affiliated with, endorsed by, sponsored by, or officially connected to any depicted individual, estate, company, or rights holder. If you redistribute or deploy this project publicly, review the image rights for your intended use case and replace assets when necessary.

## Disclaimer

This project is for research, education, and product prototyping only. It does not provide financial advice, investment recommendations, or trading guarantees. Any output should be independently verified before being used in real investment decisions.
