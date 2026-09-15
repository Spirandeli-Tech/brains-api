"""Thread isolation, transactional intake, fenced turns and durable replies."""
from datetime import datetime, timedelta
import json
import uuid

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.core.config import settings
from app.core.org_blocklist import assert_allowed
from app.models.conversation import Conversation, ConversationTurn, ConversationDelivery
from app.models.user import User

LEASE_SECONDS = 90
TERMINAL = {"succeeded", "waiting_input", "failed", "cancelled"}


def enqueue_reply(db, conversation_id, key, text, **kwargs):
    assert_allowed(text)
    # Slack limits text size; preserve the complete answer in the turn record.
    for index, start in enumerate(range(0, len(text) or 1, 3500)):
        dedupe = f"{key}:{index}"
        if not db.query(ConversationDelivery.id).filter_by(dedupe_key=dedupe).first():
            db.add(ConversationDelivery(conversation_id=conversation_id,
                dedupe_key=dedupe, text=text[start:start + 3500], **kwargs))


def receive(db, payload):
    """Called before Socket Mode ACK; commit is the durable inbox boundary."""
    event = payload.get("event") or {}
    if event.get("type") != "message" or event.get("bot_id"):
        return
    if event.get("subtype") not in (None, "file_share") or event.get("channel_type") != "im":
        return
    expected = (settings.SLACK_WORKSPACE_ID, settings.SLACK_APPLICATION_ID,
                settings.SLACK_USER_ID, settings.SLACK_BRAINS_USER_ID)
    if not all(expected):
        raise RuntimeError("Slack conversations require explicit workspace, app and operator mapping")
    if (payload.get("team_id"), payload.get("api_app_id"), event.get("user")) != expected[:3]:
        return
    operator = db.get(User, uuid.UUID(expected[3]))
    if operator is None or operator.deleted_at is not None:
        raise RuntimeError("Slack operator is not an active Brains user")
    channel, ts, event_id = event.get("channel"), event.get("ts"), payload.get("event_id")
    if not channel or not ts or not event_id:
        raise ValueError("Slack event lacks identity")
    text = (event.get("text") or "").strip()
    files = [{k: f.get(k) for k in ("id", "name", "mimetype", "size", "url_private_download", "url_private")}
             for f in event.get("files", [])][:10]
    if not text and not files:
        return
    assert_allowed(json.dumps({"text": text, "files": files}, ensure_ascii=False))
    root = event.get("thread_ts") or ts
    # A concurrent first reply can race thread creation; unique constraints are
    # authoritative, and retry acquires the winner's conversation lock.
    for attempt in range(3):
        try:
            if db.query(ConversationTurn.id).filter_by(event_id=event_id).first():
                return
            conv = db.query(Conversation).filter_by(workspace_id=expected[0], app_id=expected[1],
                channel_id=channel, thread_ts=root).with_for_update().first()
            if conv is None:
                conv = Conversation(user_id=operator.id, workspace_id=expected[0], app_id=expected[1],
                                    channel_id=channel, thread_ts=root)
                db.add(conv)
                db.flush()
            if conv.user_id != operator.id:
                raise HTTPException(403, "Conversation owner mismatch")
            if db.query(ConversationTurn.id).filter_by(conversation_id=conv.id, message_ts=ts).first():
                return
            turn = ConversationTurn(conversation_id=conv.id, event_id=event_id,
                message_ts=ts, sequence=conv.next_sequence, prompt=text or "Analise os arquivos anexados.", files=files)
            conv.next_sequence += 1
            db.add(turn)
            db.flush()
            command = text.casefold().strip()
            # Controls only inside a thread. A root always starts a fresh chat.
            if event.get("thread_ts") and command in ("status", "/status", "cancelar", "/cancelar"):
                active = db.query(ConversationTurn).filter(ConversationTurn.conversation_id == conv.id,
                    ConversationTurn.id != turn.id, ConversationTurn.status.in_(["queued", "running"])).all()
                if "cancelar" in command:
                    for item in active:
                        item.cancel_requested = True
                        if item.status == "queued":
                            item.status, item.finished_at = "cancelled", datetime.utcnow()
                    response = "Cancelamento solicitado; vou interromper a execução local. Ações externas já iniciadas podem continuar." if active else "Nenhuma execução ativa nesta thread."
                else:
                    response = "\n".join(f"{t.status}: {t.progress or 'Aguardando execução'}" for t in active) or "Nenhuma execução ativa nesta thread."
                turn.status, turn.response, turn.finished_at = "succeeded", response, datetime.utcnow()
                enqueue_reply(db, conv.id, turn.id + ":control", response)
            else:
                enqueue_reply(db, conv.id, turn.id + ":received", "Pedido registrado nesta thread. Vou executar assim que o runner estiver disponível.")
            db.commit()
            return turn.id
        except IntegrityError:
            db.rollback()
            if attempt == 2:
                raise


def expire_turns(db):
    now = datetime.utcnow()
    for turn in db.query(ConversationTurn).filter(ConversationTurn.status == "running",
            ConversationTurn.lease_until < now).with_for_update(skip_locked=True).all():
        turn.status, turn.finished_at = "failed", now
        turn.error = "Runner perdeu a conexão. Execução interrompida; efeitos externos precisam ser conferidos antes de repetir."
        enqueue_reply(db, turn.conversation_id, turn.id + ":expired", turn.error)
    db.commit()


def claim(db, runner_id, host_id, cwd):
    assert_allowed(runner_id, host_id, cwd)
    expire_turns(db)
    running = aliased(ConversationTurn)
    pending = db.query(ConversationTurn.id).filter(ConversationTurn.conversation_id == Conversation.id,
                                                  ConversationTurn.status == "queued").exists()
    busy = db.query(running.id).filter(running.conversation_id == Conversation.id, running.status == "running").exists()
    conv = db.query(Conversation).filter(pending, ~busy,
        or_(Conversation.session_host.is_(None), Conversation.session_host == host_id),
        or_(Conversation.session_cwd.is_(None), Conversation.session_cwd == cwd)
    ).order_by(Conversation.created_at).with_for_update(skip_locked=True).first()
    if conv is None:
        return None
    turn = db.query(ConversationTurn).filter_by(conversation_id=conv.id, status="queued").order_by(ConversationTurn.sequence).first()
    conv.session_host, conv.session_cwd = host_id, cwd
    turn.status, turn.runner_id, turn.claim_token = "running", runner_id, str(uuid.uuid4())
    turn.lease_until = datetime.utcnow() + timedelta(seconds=LEASE_SECONDS)
    history = db.query(ConversationTurn).filter(ConversationTurn.conversation_id == conv.id,
        ConversationTurn.sequence < turn.sequence).order_by(ConversationTurn.sequence.desc()).limit(30).all()[::-1]
    result = {"id": turn.id, "conversation_id": conv.id, "claim_token": turn.claim_token,
        "session_id": conv.session_id, "prompt": turn.prompt, "files": turn.files,
        "history": [{"prompt": t.prompt[-8000:], "response": (t.response or "")[-8000:], "status": t.status} for t in history]}
    assert_allowed(json.dumps(result, ensure_ascii=False))
    enqueue_reply(db, conv.id, turn.id + ":started", "Comecei a trabalhar. Você pode responder nesta thread; use `status` ou `cancelar` durante a execução.")
    db.commit()
    return result


def owned_turn(db, turn_id, token):
    turn = db.query(ConversationTurn).filter_by(id=turn_id).with_for_update().first()
    if turn is None or turn.claim_token != token:
        raise HTTPException(409, "Turn claim no longer belongs to this worker")
    return turn


def update(db, turn_id, data):
    assert_allowed(json.dumps(data, ensure_ascii=False))
    turn = owned_turn(db, turn_id, data["claim_token"])
    status = data.get("status")
    if turn.status in TERMINAL:
        if status == turn.status:
            return {"cancel_requested": turn.cancel_requested, "status": turn.status}
        raise HTTPException(409, "Turn is already terminal")
    if turn.lease_until < datetime.utcnow():
        raise HTTPException(409, "Turn lease expired")
    turn.lease_until = datetime.utcnow() + timedelta(seconds=LEASE_SECONDS)
    if data.get("session_id"):
        db.get(Conversation, turn.conversation_id).session_id = data["session_id"]
    if data.get("progress"):
        turn.progress = data["progress"][:2000]
        # One durable milestone per 30-second bucket; never forward raw tool output.
        bucket = int(datetime.utcnow().timestamp() // 30)
        enqueue_reply(db, turn.conversation_id, f"{turn.id}:progress:{bucket}", turn.progress)
    if status in TERMINAL:
        turn.status = "cancelled" if turn.cancel_requested else status
        turn.response, turn.error = data.get("response"), data.get("error")
        turn.cost_usd = data.get("cost_usd")
        turn.finished_at = datetime.utcnow()
        response = "Execução local cancelada." if turn.status == "cancelled" else (turn.response or turn.error or "Turno concluído.")
        enqueue_reply(db, turn.conversation_id, turn.id + ":result", response)
    db.commit()
    return {"cancel_requested": turn.cancel_requested, "status": turn.status}
