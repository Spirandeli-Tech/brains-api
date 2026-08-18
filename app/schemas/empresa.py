from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

# --- Agents ---


class AgentRead(BaseModel):
    id: UUID
    slug: str
    human_name: str
    role: str
    area: str
    reports_to: str | None = None
    bio: str | None = None
    skills: list[str] = []
    enabled: bool
    # derivado das tasks: idle | running | queued
    status: str = "idle"
    current_skill: str | None = None
    current_task_detail: str | None = None
    queued_count: int = 0
    total_cost_usd: float = 0.0

    class Config:
        from_attributes = True


class AgentSeedItem(BaseModel):
    slug: str
    human_name: str
    role: str
    area: str
    reports_to: str | None = None
    bio: str | None = None
    skills: list[str] = []


class AgentSeedRequest(BaseModel):
    agents: list[AgentSeedItem]


# --- Messages ---


class MessageRead(BaseModel):
    id: UUID
    from_agent: str
    to_agent: str | None = None
    body: str
    artifact_url: str | None = None
    task_id: UUID | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class InvestorMessageCreate(BaseModel):
    """Mensagem do investidor — protocolo do canal único: sempre para o CEO."""

    body: str
    artifact_url: str | None = None


class RunnerMessageCreate(BaseModel):
    from_agent: str
    to_agent: str | None = None
    body: str
    artifact_url: str | None = None
    # skill a enfileirar no destinatário; default atender-mensagem
    skill: str | None = None
    # False para informes que não pedem ação (reports pra cima)
    enqueue: bool = True


# --- Tasks ---


class TaskRead(BaseModel):
    id: UUID
    agent_slug: str
    skill: str
    trigger: str
    payload: dict
    status: str
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    result_summary: str | None = None
    cost_usd: float | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class TaskCreate(BaseModel):
    agent_slug: str
    skill: str
    trigger: str = "manual"
    payload: dict = {}


# --- Runner-facing ---


class ClaimRequest(BaseModel):
    runner_id: str


class TaskReport(BaseModel):
    status: str | None = None
    error: str | None = None
    result_summary: str | None = None
    cost_usd: float | None = None
