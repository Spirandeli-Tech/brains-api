"""Slack notifier — fase 3 of the proactive platform.

One-way for now: the platform reaches the operator by DM so that work waiting
on them, new proposals, and failures don't die in the DB until they open
`/briefing`. Enabled purely by env (`SLACK_BOT_TOKEN` + `SLACK_USER_ID`
present), mirroring `RUNNER_TOKEN` — there is no per-user preference row because
`platform_events` are global to the single operator.

Every send is best-effort: a Slack outage logs a warning, never raises, and
never blocks the run whose event triggered it. Routing lives in
`_target_channel`, by category to a dedicated channel (fase 3.1):
- `run_failed` (any source) → failures channel
- `awaiting_approval` / `proposal_created` → approvals channel
- `run_finished` from `code_review` → code-review channel
- the daily digest → its own channel
Precedence is by event_type first, so a code-review awaiting approval lands in
the approvals channel, not the code-review one. Each category falls back to the
operator DM when its channel env var is empty — so an unconfigured deployment
behaves exactly like the old single-DM notifier. `run_started` and other
finishes stay silent (visible in the UI, not worth a ping).

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

_EMOJI = {
    "awaiting_approval": "⏳",
    "proposal_created": "💡",
    "run_failed": "⚠️",
    "run_finished": "✅",
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


def _send(text: str, channel: str | None, blocks: list[dict] | None = None) -> None:
    """Post a mrkdwn message to a resolved Slack channel id. No-op if the channel
    couldn't be resolved (unconfigured / DM open failed). When `blocks` is given,
    `text` is sent as the notification fallback and the blocks carry the layout
    (needed for interactive buttons)."""
    if not channel:
        return
    payload: dict = {"channel": channel, "text": text}
    if blocks:
        payload["blocks"] = blocks
    _post("chat.postMessage", payload)


def _action_blocks(text: str, actions: list[dict]) -> list[dict]:
    """Block Kit layout: the message text as a section, then a row of buttons.

    Each action is {text, action_id, style?, value} — `value` carries the run/step
    ids the Socket Mode handler needs to act (see app/slack/actions.py)."""
    buttons = []
    for a in actions:
        btn = {
            "type": "button",
            "text": {"type": "plain_text", "text": a["text"], "emoji": True},
            "action_id": a["action_id"],
            "value": a.get("value", ""),
        }
        if a.get("style"):
            btn["style"] = a["style"]
        buttons.append(btn)
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {"type": "actions", "elements": buttons},
    ]


def _target_channel(event_type: str, source: str) -> str | None:
    """Resolve the channel id for an event, or None if it shouldn't notify.

    Precedence is by event_type (failures, then approvals) before source, so a
    code-review awaiting approval routes to the approvals channel. Each category
    falls back to the operator DM when its channel env var is empty.
    """
    if event_type == "run_failed":
        configured = settings.SLACK_CHANNEL_FAILURES
    elif event_type in ("awaiting_approval", "proposal_created"):
        configured = settings.SLACK_CHANNEL_APPROVALS
    elif event_type == "run_finished" and source == "code_review":
        configured = settings.SLACK_CHANNEL_CODE_REVIEW
    else:
        return None  # UI-only — not worth a ping
    return configured or _dm()


def notify_event(
    *,
    event_type: str,
    source: str,
    title: str,
    summary: str | None = None,
    detail: str | None = None,
    actions: list[dict] | None = None,
    connection_name: str | None = None,
    url_path: str | None = None,
) -> None:
    """Best-effort Slack ping for one routed platform event. Called from
    emit_event.

    `detail` is a pre-formatted mrkdwn block (built by the caller from the run +
    step) with the extra context needed to act from the phone — who opened it,
    which repo, and the drafted review/fixes/plan. It's Slack-only (not stored on
    the event), so the UI feed stays terse while the ping is self-contained.

    Silently returns for non-routed event_types and when Slack isn't configured,
    so the emit_event call site stays a plain one-liner.
    """
    if not is_configured():
        return
    channel = _target_channel(event_type, source)
    if not channel:
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

    if detail:
        lines.append(detail)

    link = _deep_link(url_path)
    if link:
        lines.append(f"<{link}|Abrir no Brains →>")

    text = "\n".join(lines)
    # Only render buttons when Socket Mode can actually handle the click — an
    # app-level token must be configured (the listener runs in the scheduler).
    # Otherwise the message would show inert buttons.
    show_actions = bool(actions and settings.SLACK_APP_TOKEN)
    blocks = _action_blocks(text, actions) if show_actions else None
    _send(text, channel, blocks)


def notify_digest(briefing: dict) -> None:
    """Morning digest — the /briefing rendered as a scannable Slack message,
    posted once a day by the scheduler."""
    if not is_configured():
        return

    channel = settings.SLACK_CHANNEL_DIGEST or _dm()
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

    _send("\n".join(lines), channel)
