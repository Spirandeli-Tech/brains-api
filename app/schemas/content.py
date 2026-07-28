from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


# --- Ideas ---


class IdeaCheckRead(BaseModel):
    """Um check já resolvido: a definição (vinda do serviço) + o veredito."""

    key: str
    label: str
    # Qual regra do principios-video.md/persona ele cobra
    rule: str
    blocking: bool
    derived: bool
    help: str
    # pass | partial | fail | unknown
    state: str
    note: str | None


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
    # Score e gate são calculados no serviço (score_idea) para que tabela e página
    # de detalhe nunca discordem — a UI não recalcula nada.
    score: int
    # approved | at_risk | unassessed | rejected. O gate manda mais que o score:
    # o filtro de tema é eliminatório no principios-video.md.
    gate: str
    checks: list[IdeaCheckRead]
    blocking_failed: list[str]
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
    checks: dict | None = None
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
    checks: dict | None = None


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
    topics_md: str | None
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


class TopicsGenerateRead(BaseModel):
    """A Gemini draft of the recording cue — never persisted on its own; the
    user edits it in the UI and confirms via `TopicsUpdate`."""

    topics_md: str


class TopicsUpdate(BaseModel):
    topics_md: str


# --- Videos ---


class VideoRead(BaseModel):
    id: UUID
    idea_id: UUID | None
    idea_title: str | None
    parent_id: UUID | None
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
    derivative_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VideoDetailRead(VideoRead):
    scripts: list[VideoScriptRead]
    derivatives: list[VideoRead]


class DerivativeCreate(BaseModel):
    """A cut or podcast hanging off an episode. Inherits the episode's idea,
    keyword and series when not given."""

    format: str = "short"
    title: str | None = None
    keyword: str | None = None
    publish_date: date | None = None
    status: str | None = None


class CadenceWeek(BaseModel):
    week_number: int
    starts_on: date
    ends_on: date
    is_current: bool
    counts: dict[str, int]
    target: dict[str, int]
    missing: dict[str, int]
    # empty | partial | complete
    state: str
    series: list[str]
    # Números dos episódios da semana — desfaz a ambiguidade entre semana do
    # plano (26 semanas, sem 1 = carga) e semana da série (ep1 = primeira).
    episodes: list[int]
    video_ids: list[UUID]


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
