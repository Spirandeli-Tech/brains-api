"""Socket Mode listener — turns interactive Slack button clicks into actions.

Fase 4 of the proactive platform: the operator gets an approval message in Slack
with Approve / Discard buttons and can act from the phone. Because the api runs on
localhost with no public URL, we use Socket Mode — an outbound WebSocket the app
opens to Slack — instead of an HTTP Request URL. The listener runs inside the
scheduler process (long-lived, has DB + services).

No-op unless both SLACK_APP_TOKEN (xapp-…, scope connections:write) and
SLACK_BOT_TOKEN are set. Best-effort throughout: a handler error is logged and
never crashes the socket. Only the configured operator (SLACK_USER_ID) may act.

Scope for now: code-review approvals (action_ids cr_approve / cr_discard). The
button `value` carries {run_id, step_id} so the click maps back to the run.
"""
from __future__ import annotations

import json
import logging

from app.core.config import settings

logger = logging.getLogger("slack.actions")

# Module-level ref so the connection (and its threads) isn't garbage-collected.
_client = None


def start_socket_mode() -> None:
    """Open the Socket Mode connection if configured. Non-blocking — the client
    runs its own background threads, so the caller (scheduler) continues its loop."""
    global _client
    if not (settings.SLACK_APP_TOKEN and settings.SLACK_BOT_TOKEN):
        logger.info("Socket Mode off (set SLACK_APP_TOKEN + SLACK_BOT_TOKEN to enable buttons).")
        return
    try:
        from slack_sdk.socket_mode import SocketModeClient
        from slack_sdk.web import WebClient

        _client = SocketModeClient(
            app_token=settings.SLACK_APP_TOKEN,
            web_client=WebClient(token=settings.SLACK_BOT_TOKEN),
        )
        _client.socket_mode_request_listeners.append(_handle)
        _client.connect()
        logger.info("Socket Mode connected — approval buttons are live.")
    except Exception:  # noqa: BLE001
        logger.exception("Could not start Socket Mode listener")


def _handle(client, req) -> None:
    from slack_sdk.socket_mode.response import SocketModeResponse

    if req.type != "interactive":
        return
    # Ack every interactive envelope immediately (Slack requires < 3s), then work.
    client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

    payload = req.payload or {}
    if payload.get("type") != "block_actions":
        return
    try:
        _dispatch(client, payload)
    except Exception:  # noqa: BLE001
        logger.exception("Slack action handler failed")


def _dispatch(client, payload: dict) -> None:
    from app.core.db import SessionLocal
    from app.services import code_review_service as cr

    actions = payload.get("actions") or []
    if not actions:
        return
    action = actions[0]
    action_id = action.get("action_id")
    user_id = (payload.get("user") or {}).get("id")
    container = payload.get("container") or {}
    channel = container.get("channel_id") or (payload.get("channel") or {}).get("id")
    ts = container.get("message_ts") or (payload.get("message") or {}).get("ts")

    # Only the operator may approve/discard — a stray channel member can't.
    if settings.SLACK_USER_ID and user_id != settings.SLACK_USER_ID:
        if channel and user_id:
            try:
                client.web_client.chat_postEphemeral(
                    channel=channel, user=user_id,
                    text="Você não tem permissão pra agir por aqui.",
                )
            except Exception:  # noqa: BLE001
                pass
        return

    try:
        ref = json.loads(action.get("value") or "{}")
    except ValueError:
        ref = {}
    run_id, step_id = ref.get("run_id"), ref.get("step_id")
    if not run_id or not step_id:
        return

    db = SessionLocal()
    try:
        run = cr.get_run(db, run_id)
        if run is None:
            _update(client, channel, ts, "⚠️ Review não encontrada.")
            return

        if action_id == "cr_approve":
            step = next((s for s in run.steps if str(s.id) == str(step_id)), None)
            if step is None or step.status != "awaiting_approval":
                _update(client, channel, ts, "ℹ️ Essa review já foi processada.")
                return
            plan = run.review_plan or {}
            cr.approve_step(
                db, run, step.id,
                review_action=plan.get("action") or "comment",
                review_plan=run.review_plan,
            )
            _update(client, channel, ts,
                    f"✅ *Aprovado por você* — PR {run.pr_number or run.pr_url} será postado.")
        elif action_id == "cr_discard":
            if run.status in cr.TERMINAL_RUN_STATUSES:
                _update(client, channel, ts, "ℹ️ Essa review já foi processada.")
                return
            cr.cancel_run(db, run)
            _update(client, channel, ts,
                    f"🗑️ *Descartado* — PR {run.pr_number or run.pr_url} não será postado.")
    finally:
        db.close()


def _update(client, channel, ts, text: str) -> None:
    """Replace the original message's buttons with a final status line, so it
    can't be clicked again."""
    if not channel or not ts:
        return
    try:
        client.web_client.chat_update(
            channel=channel, ts=ts, text=text,
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": text}}],
        )
    except Exception:  # noqa: BLE001
        logger.exception("chat_update failed")
