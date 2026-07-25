"""Read-only aggregation for the Devocionais listing page.

The 4 devocional skills (`devocional-nova-reflexao`, `devocional-preparar-semana`,
`devocional-enviar-hoje`, `devocional-narrar-video`) already write directly to 3
places on disk — this module never writes to any of them, it only reads and
merges, live, on every request:

  1. Markdown frontmatter in `DEVOCIONAL_CONTENT_DIR` — one file per day
     (`YYYY-MM-DD-<slug>.md`), the source of truth for título/data/publicado.
  2. The Telegram-sent ledger at `DEVOCIONAL_LEDGER_PATH` — whether and when a
     slug was sent to the channel.
  3. `DEVOCIONAL_VIDEOS_DIR/<slug>/meta.yaml` — narrated-video status and
     YouTube URLs, when a video exists for that slug.

Deliberately no new Postgres table: a synced mirror would be a second source of
truth to keep aligned with 3 writers that don't know about it. Any of the 3
sources being absent (e.g. local dev without the bind mounts) degrades to an
empty/partial result rather than raising — same "nothing there is not an
error" posture as `devocional-enviar-hoje`.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

import yaml

from app.core.config import settings

_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-(.+)\.md$")


def _parse_frontmatter(text: str) -> dict | None:
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    return yaml.safe_load(parts[1]) or {}


def _load_ledger() -> dict[str, datetime]:
    path = Path(settings.DEVOCIONAL_LEDGER_PATH)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    sent_at: dict[str, datetime] = {}
    for slug, entry in (data.get("sent") or {}).items():
        at = entry.get("at")
        if at:
            sent_at[slug] = datetime.fromisoformat(at)
    return sent_at


def _load_video_meta() -> dict[str, dict]:
    videos_dir = Path(settings.DEVOCIONAL_VIDEOS_DIR)
    if not videos_dir.is_dir():
        return {}
    by_slug: dict[str, dict] = {}
    for meta_path in videos_dir.glob("*/meta.yaml"):
        try:
            meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        slug = meta.get("slug") or meta_path.parent.name
        by_slug[slug] = meta
    return by_slug


def list_devocionais() -> list[dict]:
    content_dir = Path(settings.DEVOCIONAL_CONTENT_DIR)
    if not content_dir.is_dir():
        return []

    ledger = _load_ledger()
    video_meta = _load_video_meta()
    today = date.today()

    rows: list[dict] = []
    for md_path in content_dir.glob("*.md"):
        match = _FILENAME_RE.match(md_path.name)
        if not match:
            continue
        slug = match.group(1)

        try:
            frontmatter = _parse_frontmatter(md_path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if frontmatter is None or "data" not in frontmatter:
            continue

        item_date = frontmatter["data"]
        if isinstance(item_date, str):
            item_date = date.fromisoformat(item_date)
        publicado = bool(frontmatter.get("publicado", False))
        if not publicado:
            blog_status = "draft"
        elif item_date > today:
            blog_status = "scheduled"
        else:
            blog_status = "published"

        video = video_meta.get(slug)
        long_info = (video or {}).get("long") or {}
        short_info = (video or {}).get("short") or {}

        rows.append(
            {
                "slug": slug,
                "titulo": frontmatter.get("titulo", slug),
                "data": item_date,
                "versiculo": frontmatter.get("versiculo"),
                "resumo": frontmatter.get("resumo"),
                "blog_url": f"https://devocional.spirandeli.com/conteudos/{slug}",
                "blog_status": blog_status,
                "telegram_sent_at": ledger.get(slug),
                "video_status": (video or {}).get("status", "none"),
                "video_youtube_url": long_info.get("youtube_url"),
                "video_short_youtube_url": short_info.get("youtube_url"),
            }
        )

    rows.sort(key=lambda r: r["data"], reverse=True)
    return rows
