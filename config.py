from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class AnthropicConfig:
    api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    default_model: str = "claude-sonnet-4-6"


@dataclass
class ModelRegistry:
    _registry: dict[str, str] = field(default_factory=lambda: {
        "orchestrator":      "claude-sonnet-4-6",
        "data_ingestion":    "claude-haiku-4-5-20251001",
        "anomaly_detection": "claude-sonnet-4-6",
        "forecasting":       "claude-sonnet-4-6",
        "report_generator":  "claude-sonnet-4-6",
    })

    def get(self, agent_name: str) -> str:
        try:
            return self._registry[agent_name]
        except KeyError:
            raise ValueError(f"Unknown agent '{agent_name}'. Valid agents: {list(self._registry)}")

    def all(self) -> dict[str, str]:
        return dict(self._registry)


@dataclass
class OutputConfig:
    output_dir: Path = field(default_factory=lambda: Path("output"))
    dashboard_filename: str = "cfo_dashboard.html"

    @property
    def dashboard_path(self) -> Path:
        return self.output_dir / self.dashboard_filename

    def ensure_output_dir(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)


@dataclass
class Config:
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    models: ModelRegistry = field(default_factory=ModelRegistry)
    output: OutputConfig = field(default_factory=OutputConfig)


# Module-level singleton — import this throughout the project
config = Config()
