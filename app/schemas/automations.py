from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


class AutomationRunRead(BaseModel):
    id: UUID
    scheduled_for: date
    status: str
    is_manual: bool
    log: str | None
    result_summary: str | None
    error: str | None
    claimed_by: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class AutomationRead(BaseModel):
    id: UUID
    name: str
    skill: str
    instructions: str | None
    connection_name: str | None
    work_dir: str | None
    frequency: str
    day_of_week: int | None
    day_of_month: int | None
    days_of_week: list[int] | None
    time_of_day: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    recent_runs: list[AutomationRunRead]

    class Config:
        from_attributes = True


class AutomationCreate(BaseModel):
    name: str
    skill: str
    instructions: str | None = None
    connection_name: str | None = None
    work_dir: str | None = None
    frequency: str
    day_of_week: int | None = None
    day_of_month: int | None = None
    days_of_week: list[int] | None = None
    time_of_day: str | None = None


class AutomationUpdate(BaseModel):
    name: str | None = None
    skill: str | None = None
    instructions: str | None = None
    connection_name: str | None = None
    work_dir: str | None = None
    frequency: str | None = None
    day_of_week: int | None = None
    day_of_month: int | None = None
    days_of_week: list[int] | None = None
    time_of_day: str | None = None
    enabled: bool | None = None


class ClaimAutomationRequest(BaseModel):
    runner_id: str


class AutomationRunClaim(BaseModel):
    id: UUID
    automation_id: UUID
    skill: str
    instructions: str | None
    connection_name: str | None
    work_dir: str | None
    scheduled_for: date

    class Config:
        from_attributes = True


class AutomationRunUpdate(BaseModel):
    status: str | None = None
    log: str | None = None
    result_summary: str | None = None
    error: str | None = None
