from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.proposals import ProposalRead


class EventRead(BaseModel):
    id: UUID
    occurred_at: datetime
    source: str
    event_type: str
    title: str
    summary: str | None
    connection_name: str | None
    ref_kind: str | None
    ref_id: str | None
    url_path: str | None
    seen_at: datetime | None


class AwaitingItem(BaseModel):
    source: str
    ref_id: str
    title: str
    url_path: str
    connection_name: str | None


class BriefingRead(BaseModel):
    date: date
    narrative: str
    awaiting_approval: list[AwaitingItem]
    proposals: list[ProposalRead]
    done: list[EventRead]
    failures: list[EventRead]
    timeline: list[EventRead]
    unseen_count: int
