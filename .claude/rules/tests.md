---
globs: tests/*.py
---

# Testing Rules

- Use pytest with async support (pytest-asyncio)
- Each test file corresponds to one agent
- Test categories per agent:
  1. Happy path with valid sample data
  2. Edge cases: empty input, malformed data, missing columns
  3. Tool execution: verify tools produce correct output
  4. Error handling: API failures, invalid tool responses
- Use fixtures for sample data (conftest.py)
- Mock Anthropic API calls in unit tests
- Integration tests call real API (mark with @pytest.mark.integration)