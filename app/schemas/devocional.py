from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class DevocionalRead(BaseModel):
    """One reflection, merged live from the 3 places the skills write to:
    the markdown frontmatter (blog), the Telegram-sent ledger, and the
    narrated-video meta.yaml. Read-only — nothing writes through this model."""

    slug: str
    titulo: str
    data: date
    versiculo: str | None
    resumo: str | None
    blog_url: str
    # draft (publicado: false) | scheduled (publicado: true, data no futuro) | published
    blog_status: str
    telegram_sent_at: datetime | None
    # none | assembled | published
    video_status: str
    video_youtube_url: str | None
    video_short_youtube_url: str | None


class DevocionalDetail(DevocionalRead):
    """The single-reflection view — everything `DevocionalRead` has, plus the
    full blog body (`roteiro`), the condensed Telegram message, and the
    narrated-video fields the list doesn't need."""

    tema: str | None
    tags: list[str] = []
    imagem: str | None
    roteiro: str
    telegram_mensagem: str | None
    video_title: str | None
    video_thumbnail_text: str | None
    video_published_at: date | None
    video_playlist_url: str | None
