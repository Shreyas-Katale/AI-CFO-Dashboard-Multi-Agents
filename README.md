# AI CFO Dashboard — Multi-Agent System

> 🚧 **Work in Progress** — Active development. Core infrastructure is complete; agents are being built incrementally.

An AI-powered CFO dashboard built on a multi-agent architecture using Anthropic Claude. It ingests raw financial data, detects anomalies, generates forecasts, and produces an executive HTML dashboard — all coordinated by a pipeline of specialized AI agents.

---

## Architecture

```
main.py
  └── OrchestratorAgent
        ├── DataIngestionAgent      (claude-haiku-4-5)
        ├── AnomalyDetectionAgent   (claude-sonnet-4-6)  ─┐ parallel
        ├── ForecastingAgent        (claude-sonnet-4-6)  ─┘
        └── ReportGeneratorAgent    (claude-sonnet-4-6)
                  └── output/cfo_dashboard.html
```

Agents communicate via a `MessageBus` using typed Pydantic messages. Each agent runs an Anthropic tool-use loop, logs token usage and cost, and validates output before passing it downstream.

---

## Build Status

| Component | Status |
|-----------|--------|
| `config.py` — Config & model registry | ✅ Done |
| `message_bus.py` — MessageBus, Pydantic models | ✅ Done |
| `agents/base_agent.py` — Abstract BaseAgent | ✅ Done |
| `agents/data_ingestion.py` — DataIngestionAgent | ✅ Done |
| `agents/anomaly_detection.py` | 🔲 Pending |
| `agents/forecasting.py` | 🔲 Pending |
| `agents/report_generator.py` | 🔲 Pending |
| `agents/orchestrator.py` | 🔲 Pending |
| `main.py` — CLI entry point | 🔲 Pending |
| Tests — DataIngestion (10/10 passing) | ✅ Done |
| Tests — Other agents | 🔲 Pending |
| HTML Dashboard output | 🔲 Pending |

---

## What It Does

1. **Data Ingestion** — reads CSV/Excel financial files, auto-detects column schema, cleans and normalizes records, computes a 0–100 data quality score
2. **Anomaly Detection** *(coming)* — flags statistical outliers, duplicate transactions, unusual vendors, and budget breaches
3. **Forecasting** *(coming)* — projects 30/60/90-day cash flow and revenue using historical trends
4. **Report Generation** *(coming)* — assembles an interactive HTML dashboard with KPI cards, anomaly alerts, forecast charts, and an executive narrative

---

## Tech Stack

- **AI**: [Anthropic Claude](https://anthropic.com) (`claude-sonnet-4-6`, `claude-haiku-4-5`) via tool-use API
- **Data**: pandas, numpy, openpyxl
- **Validation**: Pydantic v2
- **CLI / Output**: Rich, Plotly, Jinja2
- **Tests**: pytest + pytest-asyncio
- **Config**: python-dotenv

---

## Project Structure

```
.
├── agents/
│   ├── base_agent.py          # Abstract BaseAgent (tool-use loop, retry, logging)
│   ├── data_ingestion.py      # ✅ Reads, cleans, and scores financial files
│   ├── anomaly_detection.py   # 🔲 Coming
│   ├── forecasting.py         # 🔲 Coming
│   ├── report_generator.py    # 🔲 Coming
│   └── orchestrator.py        # 🔲 Coming
├── prompts/
│   └── data_ingestion.md      # System prompt per agent
├── sample_data/
│   ├── transactions.csv       # 100-row transaction history
│   ├── profit_loss.csv        # 12-month P&L statement
│   └── cash_flow.xlsx         # 3-sheet cash flow (Operating/Investing/Financing)
├── tests/
│   ├── conftest.py
│   └── test_data_ingestion.py # 10 tests — all passing
├── output/                    # Generated dashboard written here
├── config.py                  # Dataclass config + model registry
├── message_bus.py             # MessageBus + Pydantic message models
├── pyproject.toml
└── main.py                    # 🔲 Coming
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- Conda environment (recommended) or virtualenv
- Anthropic API key

### Setup

```bash
# Clone the repo
git clone https://github.com/Shreyas-Katale/AI-CFO-Dashboard-Multi-Agents.git
cd AI-CFO-Dashboard-Multi-Agents

# Install dependencies (conda)
conda create -n cfo-dashboard python=3.11
conda activate cfo-dashboard
pip install -r requirements.txt   # coming — use pyproject.toml for now

# Set your API key
cp .env.example .env
# edit .env and add: ANTHROPIC_API_KEY=sk-ant-...
```

### Run Tests

```bash
pytest tests/ -v                          # unit tests (no API key needed)
pytest tests/ -v -m integration          # integration tests (requires API key)
```

### Run the Pipeline *(once main.py is complete)*

```bash
python main.py --input sample_data/transactions.csv
# Dashboard written to output/cfo_dashboard.html
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes (for real runs) | Your Anthropic API key |

Create a `.env` file in the project root:
```
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Contributing

This project is under active development. Check the build status table above to see what's next. Issues and PRs welcome once the core pipeline is stable.
