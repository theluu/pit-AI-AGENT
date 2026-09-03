from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Status(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    RESOLVED = "resolved"
    REPORTED = "reported"
    CANCELLED = "cancelled"


class IncidentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=3, max_length=4000)
    environment_id: str = "demo"
    service: str = "api"
    severity: str = "SEV-2"
    scenario_id: str = "INC-001"


class ApprovalDecision(BaseModel):
    decided_by: str = Field(default="demo-operator", min_length=2, max_length=80)
    arguments: dict[str, Any] | None = None
    confirmation: str | None = None


class Event(BaseModel):
    id: str = Field(default_factory=lambda: new_id("evt"))
    incident_id: str
    type: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)

