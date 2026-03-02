from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.data_ingestion import DataIngestionAgent
from message_bus import MessageBus

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"
TRANSACTIONS_CSV = SAMPLE_DIR / "transactions.csv"
PROFIT_LOSS_CSV  = SAMPLE_DIR / "profit_loss.csv"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def agent(tmp_path) -> DataIngestionAgent:
    """DataIngestionAgent with a stub system prompt (no real file needed)."""
    with patch.object(DataIngestionAgent, "__init__", lambda self, *a, **kw: None):
        inst = DataIngestionAgent.__new__(DataIngestionAgent)
        inst.name          = DataIngestionAgent.name
        inst.model         = DataIngestionAgent.model
        inst.tools         = DataIngestionAgent.tools
        inst.system_prompt = "You are a financial data engineer."
        inst.logger        = MagicMock()
        inst._client       = MagicMock()
    return inst


def _fake_api_response(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content    = [block]
    resp.stop_reason = "end_turn"
    resp.usage      = MagicMock(input_tokens=50, output_tokens=100)
    return resp


# ---------------------------------------------------------------------------
# 1. Happy path — transactions.csv
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_transactions_csv(agent):
    payload = json.dumps({
        "records": [{"date": "2024-01-05", "category": "Payroll", "amount": 185000,
                     "type": "expense", "account": "Operating Account",
                     "description": "Payroll", "duplicate_flag": False, "suspicious_flag": False}],
        "quality_report": {"score": 88},
    })
    with patch.object(agent, "_call_api_with_retry", new=AsyncMock(return_value=_fake_api_response(f"```json\n{payload}\n```"))):
        result = await agent.run({"file_path": str(TRANSACTIONS_CSV)})

    assert result.success
    assert "records" in result.data
    assert result.token_usage.input_tokens == 50


# ---------------------------------------------------------------------------
# 2. Happy path — profit_loss.csv
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_profit_loss_csv(agent):
    payload = json.dumps({
        "records": [{"date": "2024-01", "category": "Revenue", "amount": 412500,
                     "type": "income", "account": "Unknown", "description": "",
                     "duplicate_flag": False, "suspicious_flag": False}],
        "quality_report": {"score": 75},
    })
    with patch.object(agent, "_call_api_with_retry", new=AsyncMock(return_value=_fake_api_response(f"```json\n{payload}\n```"))):
        result = await agent.run({"file_path": str(PROFIT_LOSS_CSV)})

    assert result.success
    assert result.data.get("quality_report", {}).get("score") == 75


# ---------------------------------------------------------------------------
# 3. Edge case — empty CSV
# ---------------------------------------------------------------------------

def test_read_csv_empty(agent, tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("Date,Description,Amount,Category,Account\n")

    info = agent.read_csv_file(str(empty))

    assert info["row_count"] == 0
    assert set(info["columns"]) == {"Date", "Description", "Amount", "Category", "Account"}


# ---------------------------------------------------------------------------
# 4. Edge case — missing required columns
# ---------------------------------------------------------------------------

def test_detect_schema_missing_columns(agent, tmp_path):
    partial = tmp_path / "partial.csv"
    partial.write_text("Vendor,Notes\nAcme,Payment\n")

    result = agent.detect_schema(str(partial))
    mapping = result["column_mapping"]

    # 'description' maps to Notes; date/amount/category/account are absent
    assert "date"   not in mapping
    assert "amount" not in mapping
    assert "description" in mapping or len(result["unmapped_columns"]) > 0


# ---------------------------------------------------------------------------
# 5. Schema detection — correct mapping
# ---------------------------------------------------------------------------

def test_detect_schema_transactions_csv(agent):
    result = agent.detect_schema(str(TRANSACTIONS_CSV))
    mapping = result["column_mapping"]

    assert mapping.get("date")        == "Date"
    assert mapping.get("amount")      == "Amount"
    assert mapping.get("description") == "Description"
    assert mapping.get("category")    == "Category"
    assert mapping.get("account")     == "Account"


# ---------------------------------------------------------------------------
# 6. Quality score calculation
# ---------------------------------------------------------------------------

def test_compute_quality_score_clean(agent, sample_records):
    # Use only the 6 non-flagged records
    clean = [r for r in sample_records if not r["duplicate_flag"] and not r["suspicious_flag"]]
    result = agent.compute_quality_score(clean)

    assert result["score"] > 60
    assert result["total_rows"] == len(clean)
    assert result["flagged_duplicates"] == 0


def test_compute_quality_score_with_flags(agent, sample_records):
    result = agent.compute_quality_score(sample_records)

    assert result["flagged_duplicates"] == 2
    assert result["flagged_suspicious"] == 2
    assert "dimensions" in result


def test_compute_quality_score_empty(agent):
    result = agent.compute_quality_score([])

    assert result["score"] == 0
    assert len(result["errors"]) > 0


# ---------------------------------------------------------------------------
# 7. Deduplication — duplicate rows are flagged, not dropped
# ---------------------------------------------------------------------------

def test_clean_and_normalize_flags_duplicates(agent, tmp_path):
    csv = tmp_path / "dupes.csv"
    csv.write_text(
        "Date,Description,Amount,Category,Account\n"
        "2024-06-13,Zoom Annual Renewal,2160.00,SaaS Tools,Corporate Card\n"
        "2024-06-13,Zoom Annual Renewal,2160.00,SaaS Tools,Corporate Card\n"
        "2024-01-05,Office Supplies,320.00,Office Supplies,Corporate Card\n"
    )
    mapping = {"date": "Date", "description": "Description",
               "amount": "Amount", "category": "Category", "account": "Account"}

    records = agent.clean_and_normalize(str(csv), column_mapping=mapping)

    assert len(records) == 3  # none discarded
    dup_flags = [r["duplicate_flag"] for r in records]
    assert dup_flags[0] is True
    assert dup_flags[1] is True
    assert dup_flags[2] is False


# ---------------------------------------------------------------------------
# 8. API failure → clean error in AgentOutput
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_api_failure_returns_error_output(agent):
    with patch.object(
        agent, "_call_api_with_retry",
        new=AsyncMock(side_effect=RuntimeError("API unavailable")),
    ):
        result = await agent.run({"file_path": str(TRANSACTIONS_CSV)})

    assert not result.success
    assert any("API unavailable" in e for e in result.errors)
