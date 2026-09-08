from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    demo_mode: bool = os.getenv("AGENTOPS_DEMO_MODE", "true").lower() == "true"
    default_runtime_mode: str = os.getenv("AGENTOPS_RUNTIME_MODE", "auto")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    planner_model: str = os.getenv("AGENTOPS_PLANNER_MODEL", "gpt-5.6-terra")
    reporter_model: str = os.getenv("AGENTOPS_REPORTER_MODEL", "gpt-5.6-luna")
    max_tool_calls: int = int(os.getenv("AGENTOPS_MAX_TOOL_CALLS", "12"))
    max_replans: int = int(os.getenv("AGENTOPS_MAX_REPLANS", "3"))


settings = Settings()
