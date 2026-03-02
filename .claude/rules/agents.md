---
globs: agents/*.py
---

# Agent Development Rules

When creating or modifying any agent file:

1. MUST inherit from BaseAgent (agents/base_agent.py)
2. MUST define class attributes:
   - `name: str` — agent identifier
   - `model: str` — Anthropic model string
   - `tools: list[dict]` — tool-use JSON schemas
   - `system_prompt: str` — loaded from prompts/{name}.md
3. MUST implement `async run(self, input_data: dict) -> AgentOutput`
4. The run() method MUST:
   - Log start via self.logger
   - Call Anthropic API with tool use loop
   - Handle tool calls iteratively until complete
   - Validate output with Pydantic model
   - Log token usage and processing time
   - Return structured AgentOutput
5. MUST have error handling:
   - Retry API calls up to 3 times with exponential backoff
   - Catch and log tool execution failures
   - Return meaningful error messages in AgentOutput
6. NEVER hardcode API keys — use config.py