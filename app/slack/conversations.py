"""Single Socket Mode ingress; background delivery never blocks intake."""
from datetime import datetime, timedelta
import logging
import threading
import time

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.core.config import settings
from app.core.db import SessionLocal
from app.models.conversation import Conversation, ConversationDelivery
from app.services.conversation_service import receive, expire_turns

logger = logging.getLogger(__name__)


def receive_event(payload):
    with SessionLocal() as db:
        return receive(db, payload)


def deliver_one(db, web):
    now = datetime.utcnow()
    # A crash during a send has an unknown outcome. Do not automatically resend
    # email-like external effects or uploads after an ambiguous acknowledgement.
    for stale in db.query(ConversationDelivery).filter(ConversationDelivery.status == "sending",
            ConversationDelivery.available_at < now - timedelta(minutes=5)).with_for_update(skip_locked=True).all():
        stale.status, stale.error = "uncertain", "Delivery interrupted; reconcile in Slack before retrying."
    db.commit()
    row = db.query(ConversationDelivery).filter(ConversationDelivery.status == "pending",
        ConversationDelivery.available_at <= now).order_by(ConversationDelivery.created_at).with_for_update(skip_locked=True).first()
    if row is None:
        return False
    conv = db.get(Conversation, row.conversation_id)
    row.status, row.attempts, row.available_at = "sending", row.attempts + 1, now
    db.commit()
    try:
        if row.kind == "file":
            result = web.files_upload_v2(channel=conv.channel_id, thread_ts=conv.thread_ts,
                                        file=row.file_path, title=row.text)
            row.slack_ts = (result.get("files") or [{}])[0].get("id")
        else:
            result = web.chat_postMessage(channel=conv.channel_id, thread_ts=conv.thread_ts,
                text=row.text, client_msg_id=row.id, unfurl_links=False, unfurl_media=False)
            row.slack_ts = result.get("ts")
        row.status, row.error = "sent", None
    except SlackApiError as exc:
        error = exc.response.get("error", "slack_error")
        row.error = error
        # Retry only explicit rejection (no successful side effect). A file
        # upload is multi-step, so its failure always requires reconciliation.
        if row.kind == "text" and error == "ratelimited":
            row.status = "pending"
            row.available_at = now + timedelta(seconds=max(1, int(exc.response.headers.get("Retry-After", "30"))))
        else:
            row.status = "uncertain" if row.kind == "file" else "failed"
        logger.warning("Slack conversation delivery %s: %s", row.id, row.status)
    except Exception:
        row.status, row.error = "uncertain", "Slack response unknown; inspect delivery before retrying."
        logger.warning("Slack conversation delivery %s has an uncertain outcome", row.id)
    db.commit()
    return True


def start_delivery_worker():
    if not settings.SLACK_CONVERSATIONS_ENABLED:
        return
    def loop():
        web = WebClient(token=settings.SLACK_BOT_TOKEN, timeout=30)
        while True:
            try:
                with SessionLocal() as db:
                    expire_turns(db)
                    for _ in range(10):
                        if not deliver_one(db, web):
                            break
            except Exception:
                logger.exception("Conversation delivery cycle failed")
            time.sleep(2)
    threading.Thread(target=loop, name="slack-conversation-delivery", daemon=True).start()
