from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class WatcherRead(BaseModel):
    id: UUID
    kind: str
    connection_id: UUID | None
    connection_name: str | None
    config: dict
    interval_minutes: int
    enabled: bool
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WatcherCreate(BaseModel):
    kind: str
    connection_id: UUID | None = None
    config: dict | None = None
    interval_minutes: int | None = None


class WatcherUpdate(BaseModel):
    connection_id: UUID | None = None
    config: dict | None = None
    interval_minutes: int | None = None
    enabled: bool | None = None


class ClaimWatcherRequest(BaseModel):
    runner_id: str


class WatcherClaimRead(BaseModel):
    id: UUID
    kind: str
    connection_id: UUID | None
    connection_name: str | None
    config: dict
    interval_minutes: int

    class Config:
        from_attributes = True


class SightingReport(BaseModel):
    external_key: str
    title: str | None = None
    # PR-shaped sightings (github_review_requested)
    pr_url: str | None = None
    pr_number: str | None = None
    repo_name: str | None = None
    pr_author: str | None = None
    # Ticket-shaped sightings (jira_backlog_assigned)
    ticket_key: str | None = None
    ticket_url: str | None = None


class WatcherReport(BaseModel):
    status: str
    error: str | None = None
    sightings: list[SightingReport] = []
