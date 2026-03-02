# AI CFO Dashboard Builder

## Architecture
- Multi-agent system: 5 agents following Orchestrator-Worker pattern
- All agents inherit from BaseAgent (agents/base_agent.py)
- Inter-agent communication via MessageBus (message_bus.py)
- Each agent has: system_prompt (in prompts/), tools list, model config

## Agent Registry
| Agent | Model | File |
|-------|-------|------|
| Orchestrator | claude-sonnet-4-5-20250929 | agents/orchestrator.py |
| DataIngestion | claude-haiku-4-5-20251001 | agents/data_ingestion.py |
| AnomalyDetection | claude-sonnet-4-5-20250929 | agents/anomaly_detection.py |
| Forecasting | claude-sonnet-4-5-20250929 | agents/forecasting.py |
| ReportGenerator | claude-sonnet-4-5-20250929 | agents/report_generator.py |

## Conventions
- Type hints on ALL functions
- Pydantic models for inter-agent messages (models defined in message_bus.py)
- Every agent logs: token usage, processing time, cost estimate
- Tools defined as Anthropic tool-use JSON schemas
- All agent outputs validated via Pydantic before passing downstream
- Use Rich for CLI output (progress bars, status, tables)

## Message Schema
{id, from, to, type, timestamp, payload, metadata}
Types: TASK_START, TASK_COMPLETE, TASK_FAILED, DATA_READY, QUALITY_CHECK

## Testing
- pytest for all tests
- Each agent has unit tests in tests/test_{agent_name}.py
- Integration test in tests/test_pipeline.py

## Key Commands
- Run pipeline: python main.py --input sample_data/transactions.csv
- Run tests: pytest tests/ -v
- Single agent test: pytest tests/test_data_ingestion.py -v