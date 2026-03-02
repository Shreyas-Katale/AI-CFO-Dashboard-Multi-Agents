from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from message_bus import AgentOutput, MessageBus, TokenUsage

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SAMPLE_DIR = Path(__file__).parent.parent / "sample_data"
TRANSACTIONS_CSV = SAMPLE_DIR / "transactions.csv"
PROFIT_LOSS_CSV  = SAMPLE_DIR / "profit_loss.csv"
CASH_FLOW_XLSX   = SAMPLE_DIR / "cash_flow.xlsx"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_bus() -> MessageBus:
    return MessageBus()


@pytest.fixture()
def sample_records() -> list[dict]:
    """10 clean normalized records for unit tests."""
    return [
        {
            "date": "2024-01-05", "category": "Payroll",   "amount": 185000.0,
            "type": "expense", "account": "Operating Account",
            "description": "Employee Payroll", "duplicate_flag": False, "suspicious_flag": False,
        },
        {
            "date": "2024-01-15", "category": "Revenue",   "amount": 45000.0,
            "type": "income",  "account": "Revenue Account",
            "description": "Customer Payment - Acme Corp", "duplicate_flag": False, "suspicious_flag": False,
        },
        {
            "date": "2024-01-03", "category": "SaaS Tools", "amount": 12450.0,
            "type": "expense", "account": "Corporate Card",
            "description": "AWS Cloud Infrastructure", "duplicate_flag": False, "suspicious_flag": False,
        },
        {
            "date": "2024-01-08", "category": "Facilities", "amount": 8500.0,
            "type": "expense", "account": "Operating Account",
            "description": "Office Rent", "duplicate_flag": False, "suspicious_flag": False,
        },
        {
            "date": "2024-01-22", "category": "SaaS Tools", "amount": 18000.0,
            "type": "expense", "account": "Corporate Card",
            "description": "HubSpot CRM Annual Renewal", "duplicate_flag": False, "suspicious_flag": False,
        },
        {
            "date": "2024-01-25", "category": "Revenue",   "amount": 22500.0,
            "type": "income",  "account": "Revenue Account",
            "description": "Customer Payment - Globex Inc", "duplicate_flag": False, "suspicious_flag": False,
        },
        {
            "date": "2024-02-01", "category": "Payroll",   "amount": 185000.0,
            "type": "expense", "account": "Operating Account",
            "description": "Employee Payroll", "duplicate_flag": True,  "suspicious_flag": False,
        },
        {
            "date": "2024-02-01", "category": "Payroll",   "amount": 185000.0,
            "type": "expense", "account": "Operating Account",
            "description": "Employee Payroll", "duplicate_flag": True,  "suspicious_flag": False,
        },
        {
            "date": "2024-03-10", "category": "Unknown",   "amount": 485000.0,
            "type": "expense", "account": "Corporate Card",
            "description": "ANOMALY", "duplicate_flag": False, "suspicious_flag": True,
        },
        {
            "date": "2024-03-15", "category": "Uncategorized", "amount": 0.0,
            "type": "expense", "account": "Unknown",
            "description": "", "duplicate_flag": False, "suspicious_flag": True,
        },
    ]


@pytest.fixture()
def mock_anthropic_response():
    """Factory that returns a fake anthropic Message object."""
    def _make(text: str = '{"records": [], "quality_report": {"score": 90}}'):
        content_block = MagicMock()
        content_block.type = "text"
        content_block.text = text

        response = MagicMock()
        response.content = [content_block]
        response.stop_reason = "end_turn"
        response.usage = MagicMock(input_tokens=100, output_tokens=200)
        return response
    return _make
