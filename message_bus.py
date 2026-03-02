from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console
from rich.text import Text

console = Console()


class MessageType(str, Enum):
    TASK_START = "TASK_START"
    TASK_COMPLETE = "TASK_COMPLETE"
    TASK_FAILED = "TASK_FAILED"
    DATA_READY = "DATA_READY"
    QUALITY_CHECK = "QUALITY_CHECK"


_MSG_TYPE_STYLES: dict[MessageType, str] = {
    MessageType.TASK_START:    "bold cyan",
    MessageType.TASK_COMPLETE: "bold green",
    MessageType.TASK_FAILED:   "bold red",
    MessageType.DATA_READY:    "bold yellow",
    MessageType.QUALITY_CHECK: "bold magenta",
}


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_agent: str
    to_agent: str
    type: MessageType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    agent_name: str
    status: str                          # "success" | "failed"
    data: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    processing_time_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.status == "success"


Handler = Callable[[Message], Coroutine[Any, Any, None]]


class MessageBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = {}
        self._history: list[Message] = []

    def subscribe(self, agent_name: str, callback: Handler) -> None:
        self._subscribers.setdefault(agent_name, []).append(callback)

    async def publish(self, message: Message) -> None:
        self._history.append(message)
        self._log(message)

        handlers = self._subscribers.get(message.to_agent, [])
        await asyncio.gather(*(h(message) for h in handlers))

    def get_history(
        self,
        agent_name: str | None = None,
        msg_type: MessageType | None = None,
    ) -> list[Message]:
        messages = self._history
        if agent_name is not None:
            messages = [
                m for m in messages
                if m.from_agent == agent_name or m.to_agent == agent_name
            ]
        if msg_type is not None:
            messages = [m for m in messages if m.type == msg_type]
        return messages

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log(self, message: Message) -> None:
        style = _MSG_TYPE_STYLES.get(message.type, "white")
        ts = message.timestamp.strftime("%H:%M:%S")

        line = Text()
        line.append(f"[{ts}] ", style="dim")
        line.append(f"{message.from_agent}", style="bold blue")
        line.append(" → ", style="dim")
        line.append(f"{message.to_agent}", style="bold blue")
        line.append("  ")
        line.append(f"[{message.type.value}]", style=style)

        if message.metadata:
            meta_str = "  " + "  ".join(f"{k}={v}" for k, v in message.metadata.items())
            line.append(meta_str, style="dim")

        console.print(line)
