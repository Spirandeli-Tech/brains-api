from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


# --- Ideas ---


class IdeaRead(BaseModel):
    id: UUID
    slug: str
    title: str
    format: str
    type: str | None
    priority: str
    status: str
    hook: str | None
    why_now: str | None
    visual_refs: str | None
    trustworthy: bool
    fact_check: str | None
    theme_filter: dict
    source: str
    video_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class IdeaCreate(BaseModel):
    title: str
    slug: str | None = None
    format: str | None = None
    type: str | None = None
    priority: str | None = None
    status: str | None = None
    hook: str | None = None
    why_now: str | None = None
    visual_refs: str | None = None
    trustworthy: bool | None = None
    fact_check: str | None = None
    theme_filter: dict | None = None
    source: str | None = None


class IdeaUpdate(BaseModel):
    title: str | None = None
    slug: str | None = None
    format: str | None = None
    type: str | None = None
    priority: str | None = None
    status: str | None = None
    hook: str | None = None
    why_now: str | None = None
    visual_refs: str | None = None
    trustworthy: bool | None = None
    fact_check: str | None = None
    theme_filter: dict | None = None


class IdeaTopicRead(BaseModel):
    """Slim shape for the dedup step of `/social-buscar-trends` — the skill only
    needs to know what has already been said, not the whole row."""

    id: UUID
    slug: str
    title: str
    status: str

    class Config:
        from_attributes = True


class PromoteIdeaRequest(BaseModel):
    format: str | None = None
    publish_date: date | None = None
    keyword: str | None = None
    series: str | None = None
    episode_number: int | None = None


# --- Video scripts ---


class VideoScriptRead(BaseModel):
    id: UUID
    video_id: UUID
    version: int
    body: str
    titles: list[str]
    caption: str | None
    hashtags: list[str]
    cover: str | None
    facts_used: str | None
    growth_checklist: list[dict]
    short_cuts: list[str]
    persona: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class VideoScriptCreate(BaseModel):
    body: str
    titles: list[str] | None = None
    caption: str | None = None
    hashtags: list[str] | None = None
    cover: str | None = None
    facts_used: str | None = None
    growth_checklist: list[dict] | None = None
    short_cuts: list[str] | None = None
    persona: str | None = None


# --- Videos ---


class VideoRead(BaseModel):
    id: UUID
    idea_id: UUID | None
    idea_title: str | None
    title: str
    slug: str | None
    keyword: str | None
    format: str
    series: str | None
    episode_number: int | None
    publish_date: date | None
    status: str
    thumb_url: str | None
    youtube_url: str | None
    ctr_48h: Decimal | None
    retention_48h: Decimal | None
    learning: str | None
    script_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VideoDetailRead(VideoRead):
    scripts: list[VideoScriptRead]


class VideoCreate(BaseModel):
    title: str
    idea_id: UUID | None = None
    slug: str | None = None
    keyword: str | None = None
    format: str | None = None
    series: str | None = None
    episode_number: int | None = None
    publish_date: date | None = None
    status: str | None = None
    thumb_url: str | None = None
    youtube_url: str | None = None


class VideoUpdate(BaseModel):
    title: str | None = None
    idea_id: UUID | None = None
    slug: str | None = None
    keyword: str | None = None
    format: str | None = None
    series: str | None = None
    episode_number: int | None = None
    publish_date: date | None = None
    status: str | None = None
    thumb_url: str | None = None
    youtube_url: str | None = None
    ctr_48h: Decimal | None = None
    retention_48h: Decimal | None = None
    learning: str | None = None


# --- Runner-facing ---


class RunnerIdeaBulkCreate(BaseModel):
    """Payload for `/social-buscar-trends`: writes a batch of fact-checked ideas.

    `user_email` is explicit because the runner has no session — there is more
    than one user in this database, so guessing is not an option.
    """

    user_email: str
    ideas: list[IdeaCreate]


class RunnerScriptCreate(VideoScriptCreate):
    user_email: str
