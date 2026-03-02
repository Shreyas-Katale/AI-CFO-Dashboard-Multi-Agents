from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import anthropic
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import config
from message_bus import AgentOutput, TokenUsage

console = Console()

# Cost per million tokens (input, output) by model
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6":          (3.00,  15.00),
    "claude-sonnet-4-5-20250929":  (3.00,  15.00),
    "claude-haiku-4-5-20251001":   (0.25,   1.25),
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = _MODEL_PRICING.get(model, (3.00, 15.00))
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


class BaseAgent(ABC):
    """Abstract base for all CFO dashboard agents."""

    name: str        # set as class attribute by each subclass
    model: str       # set as class attribute by each subclass
    tools: list[dict[str, Any]]  # Anthropic tool-use JSON schemas

    def __init__(self, system_prompt_path: str | Path | None = None) -> None:
        self.logger = logging.getLogger(self.name)
        self._client = anthropic.AsyncAnthropic(api_key=config.anthropic.api_key)

        # Load system prompt from prompts/{name}.md by default
        if system_prompt_path is None:
            system_prompt_path = Path("prompts") / f"{self.name}.md"
        self.system_prompt = Path(system_prompt_path).read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def run(self, input_data: dict[str, Any]) -> AgentOutput:
        """Execute the agent's task. Must be implemented by each subclass."""
        ...

    # ------------------------------------------------------------------
    # API call with tool-use loop
    # ------------------------------------------------------------------

    async def _call_api(
        self,
        messages: list[dict[str, Any]],
        *,
        max_iterations: int = 10,
    ) -> tuple[str, TokenUsage]:
        """
        Run the full tool-use loop until the model stops or max_iterations hit.

        Returns:
            (final_text, token_usage) — final_text is the last text block from
            the model; token_usage is the cumulative total across all turns.
        """
        cumulative = TokenUsage()
        final_text = ""
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            response = await self._call_api_with_retry(messages)

            # Accumulate tokens
            cumulative.input_tokens  += response.usage.input_tokens
            cumulative.output_tokens += response.usage.output_tokens
            cumulative.cost_usd = _estimate_cost(
                self.model,
                cumulative.input_tokens,
                cumulative.output_tokens,
            )

            # Collect text from this turn
            text_blocks = [b.text for b in response.content if b.type == "text"]
            if text_blocks:
                final_text = "\n".join(text_blocks)

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                # Build the assistant turn and tool results
                messages.append({"role": "assistant", "content": response.content})
                tool_results = await self._handle_tool_calls(response.content)
                messages.append({"role": "user", "content": tool_results})
                continue

            # Any other stop reason — treat as done
            break

        return final_text, cumulative

    async def _call_api_with_retry(
        self,
        messages: list[dict[str, Any]],
        *,
        max_attempts: int = 3,
    ) -> anthropic.types.Message:
        """Call Anthropic API with exponential backoff retry (1s → 2s → 4s)."""
        import asyncio

        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                kwargs: dict[str, Any] = {
                    "model":      self.model,
                    "max_tokens": 4096,
                    "system":     self.system_prompt,
                    "messages":   messages,
                }
                if self.tools:
                    kwargs["tools"] = self.tools

                return await self._client.messages.create(**kwargs)

            except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as exc:
                last_exc = exc
                if attempt < max_attempts - 1:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    self.logger.warning(
                        "API call failed (attempt %d/%d): %s — retrying in %ds",
                        attempt + 1, max_attempts, exc, wait,
                    )
                    await asyncio.sleep(wait)

        raise RuntimeError(
            f"[{self.name}] API call failed after {max_attempts} attempts"
        ) from last_exc

    # ------------------------------------------------------------------
    # Tool dispatch
    # ------------------------------------------------------------------

    async def _handle_tool_calls(
        self, content: list[Any]
    ) -> list[dict[str, Any]]:
        """Execute all tool_use blocks and return a list of tool_result dicts."""
        results = []
        for block in content:
            if block.type != "tool_use":
                continue
            try:
                output = await self._execute_tool(block.name, block.input)
                results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     str(output),
                })
                self.logger.debug("Tool '%s' succeeded", block.name)
            except Exception as exc:  # noqa: BLE001
                self.logger.error("Tool '%s' failed: %s", block.name, exc)
                results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     f"ERROR: {exc}",
                    "is_error":    True,
                })
        return results

    async def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        """
        Dispatch a tool call to the matching method on this class.
        Subclasses define tool handler methods named exactly as the tool.
        """
        handler = getattr(self, tool_name, None)
        if handler is None:
            raise NotImplementedError(f"[{self.name}] No handler for tool '{tool_name}'")
        if asyncio.iscoroutinefunction(handler):
            return await handler(**tool_input)
        return handler(**tool_input)

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log_start(self, input_summary: str = "") -> float:
        """Log agent start and return start timestamp (monotonic)."""
        msg = Text()
        msg.append(f"▶ {self.name}", style="bold cyan")
        if input_summary:
            msg.append(f"  {input_summary}", style="dim")
        console.print(msg)
        self.logger.info("Starting — %s", input_summary)
        return time.monotonic()

    def _log_completion(
        self,
        start: float,
        token_usage: TokenUsage,
        *,
        success: bool = True,
    ) -> float:
        """Log agent completion. Returns elapsed_ms."""
        elapsed_ms = (time.monotonic() - start) * 1000

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="dim")
        table.add_column(style="white")

        status_str = "[bold green]✓ success[/]" if success else "[bold red]✗ failed[/]"
        table.add_row("status",   status_str)
        table.add_row("agent",    self.name)
        table.add_row("model",    self.model)
        table.add_row("time",     f"{elapsed_ms:,.0f} ms")
        if token_usage:
            table.add_row("tokens", f"{token_usage.input_tokens:,} in / {token_usage.output_tokens:,} out")
            table.add_row("cost",   f"${token_usage.cost_usd:.5f}")
        else:
            table.add_row("tokens", "n/a")
            table.add_row("cost",   "n/a")

        console.print(Panel(table, title=f"[bold]{'✓' if success else '✗'} {self.name}[/]", expand=False))
        if token_usage:
            self.logger.info(
                "Done in %.0f ms — %d in / %d out tokens — $%.5f",
                elapsed_ms,
                token_usage.input_tokens,
                token_usage.output_tokens,
                token_usage.cost_usd,
            )
        else:
            self.logger.info("Done in %.0f ms — no token data", elapsed_ms)
        return elapsed_ms

    def _make_output(
        self,
        *,
        success: bool,
        data: dict[str, Any] | None = None,
        errors: list[str] | None = None,
        token_usage: TokenUsage | None = None,
        processing_time_ms: float = 0.0,
    ) -> AgentOutput:
        """Convenience factory for AgentOutput."""
        return AgentOutput(
            agent_name=self.name,
            status="success" if success else "failed",
            data=data or {},
            errors=errors or [],
            token_usage=token_usage or TokenUsage(),
            processing_time_ms=processing_time_ms,
        )
