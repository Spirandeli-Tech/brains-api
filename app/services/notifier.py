"""Slack notifier — fase 3 of the proactive platform.

One-way for now: the platform reaches the operator by DM so that work waiting
on them, new proposals, and failures don't die in the DB until they open
`/briefing`. Enabled purely by env (`SLACK_BOT_TOKEN` + `SLACK_USER_ID`
present), mirroring `RUNNER_TOKEN` — there is no per-user preference row because
`platform_events` are global to the single operator.

Every send is best-effort: a Slack outage logs a warning, never raises, and
never blocks the run whose event triggered it. Routing lives in
`NOTIFY_EVENT_TYPES`: `awaiting_approval` / `proposal_created` / `run_failed`
reach out; `run_started` and the rest stay silent (visible in the UI, not worth
a ping).

Future (fase 4): make it two-way via Socket Mode — the app-level token already
issued for this app receives `message.im` events with no public URL, and a
bridge in the runner turns each into a `claude -p` reply. See
docs/features/proactive-platform/README.md §8.
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api"
_TIMEOUT_SECONDS = 5.0

# The only event_types worth a proactive ping. Everything else is UI-only, so a
# busy day doesn't turn into a stream of Slack noise.
NOTIFY_EVENT_TYPES = {"awaiting_approval", "proposal_created", "run_failed"}

_EMOJI = {
    "awaiting_approval": "⏳",
    "proposal_created": "💡",
    "run_failed": "⚠️",
}

# Kept local (not imported from platform_events_service) to avoid a circular
# import — that module imports this one to fire notifications from emit_event.
_SOURCE_LABELS = {
    "implementation": "Implementação",
    "code_review": "Code review",
    "address_pr": "Address PR",
    "automation": "Automação",
    "watcher": "Watcher",
    "planner": "Planejadora",
    "system": "Sistema",
}

# The bot's DM channel with the operator, resolved once and cached for the
# process lifetime (conversations.open is idempotent, but no need to re-hit it).
_dm_channel: str | None = None


def is_configured() -> bool:
    return bool(settings.SLACK_BOT_TOKEN and settings.SLACK_USER_ID)


def _post(method: str, payload: dict) -> dict | None:
    try:
        resp = httpx.post(
            f"{SLACK_API}/{method}",
            headers={"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"},
            json=payload,
            timeout=_TIMEOUT_SECONDS,
        )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — best-effort: a Slack hiccup must never surface
        logger.warning("Slack %s call failed: %s", method, exc)
        return None
    if not data.get("ok"):
        logger.warning("Slack %s returned error: %s", method, data.get("error"))
        return None
    return data


def _dm() -> str | None:
    global _dm_channel
    if _dm_channel:
        return _dm_channel
    data = _post("conversations.open", {"users": settings.SLACK_USER_ID})
    if data:
        _dm_channel = (data.get("channel") or {}).get("id")
    return _dm_channel


def _deep_link(url_path: str | None) -> str | None:
    if not url_path:
        return None
    base = (settings.WEB_BASE_URL or "").rstrip("/")
    return f"{base}{url_path}" if base else None


def _send(text: str) -> None:
    """Post a mrkdwn message to the operator's DM. No-op if unconfigured or the
    DM channel can't be resolved."""
    if not is_configured():
        return
    channel = _dm()
    if not channel:
        return
    _post("chat.postMessage", {"channel": channel, "text": text})


def notify_event(
    *,
    event_type: str,
    source: str,
    title: str,
    summary: str | None = None,
    connection_name: str | None = None,
    url_path: str | None = None,
) -> None:
    """Best-effort DM for one routed platform event. Called from emit_event.

    Silently returns for non-routed event_types and when Slack isn't configured,
    so the emit_event call site stays a plain one-liner.
    """
    if event_type not in NOTIFY_EVENT_TYPES or not is_configured():
        return

    emoji = _EMOJI.get(event_type, "🔔")
    lines = [f"{emoji} *{title}*"]
    if summary:
        lines.append(summary)

    context = " · ".join(
        part for part in (connection_name, _SOURCE_LABELS.get(source, source)) if part
    )
    if context:
        lines.append(f"_{context}_")

    link = _deep_link(url_path)
    if link:
        lines.append(f"<{link}|Abrir no Brains →>")

    _send("\n".join(lines))


def notify_digest(briefing: dict) -> None:
    """Morning digest — the /briefing rendered as a scannable Slack message,
    posted once a day by the scheduler."""
    if not is_configured():
        return

    lines = ["☀️ *Resumo do dia*", briefing.get("narrative") or "Bom dia."]

    def _section(header: str, items: list[dict]) -> None:
        if not items:
            return
        lines.append("")
        lines.append(f"*{header} ({len(items)})*")
        for item in items[:8]:
            lines.append(f"• {item.get('title')}")
        if len(items) > 8:
            lines.append(f"…e mais {len(items) - 8}")

    _section("⏳ Aguardando você", briefing.get("awaiting_approval") or [])
    _section("💡 Propostas", briefing.get("proposals") or [])
    _section("⚠️ Falhas", briefing.get("failures") or [])

    link = _deep_link("/briefing")
    if link:
        lines.append("")
        lines.append(f"<{link}|Abrir o briefing →>")

    _send("\n".join(lines))
