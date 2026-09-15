"""Runner transport for general agent turns and bounded artifact transfer."""
import hashlib
from pathlib import Path
import re
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.runner import require_runner
from app.core.config import settings
from app.core.db import get_db
from app.core.org_blocklist import assert_allowed
from app.models.conversation import ConversationDelivery
from app.services import conversation_service as svc

router = APIRouter(prefix="/conversations/runner", tags=["conversations"], dependencies=[Depends(require_runner)])
MAX_FILE_BYTES = 20 * 1024 * 1024


class ClaimIn(BaseModel):
    runner_id: str = Field(min_length=1, max_length=200)
    host_id: str = Field(min_length=1, max_length=200)
    cwd: str = Field(min_length=1, max_length=2000)


class UpdateIn(BaseModel):
    claim_token: str
    session_id: str | None = None
    status: str | None = None
    response: str | None = Field(default=None, max_length=100000)
    error: str | None = Field(default=None, max_length=4000)
    progress: str | None = Field(default=None, max_length=2000)
    cost_usd: str | None = None


@router.post("/claim")
def claim(data: ClaimIn, db: Session = Depends(get_db)):
    if not settings.SLACK_CONVERSATIONS_ENABLED:
        return Response(status_code=204)
    return svc.claim(db, **data.model_dump()) or Response(status_code=204)


@router.patch("/turns/{turn_id}")
def update(turn_id: str, data: UpdateIn, db: Session = Depends(get_db)):
    if data.status is not None and data.status not in svc.TERMINAL:
        raise HTTPException(422, "Invalid terminal status")
    return svc.update(db, turn_id, data.model_dump(exclude_none=True))


def active_turn(db, turn_id, claim_token):
    from datetime import datetime
    turn = svc.owned_turn(db, turn_id, claim_token)
    if turn.status != "running" or turn.cancel_requested or turn.lease_until < datetime.utcnow():
        raise HTTPException(409, "Turn is no longer active")
    return turn


@router.get("/turns/{turn_id}/files/{file_id}")
def download_file(turn_id: str, file_id: str, claim_token: str, db: Session = Depends(get_db)):
    turn = active_turn(db, turn_id, claim_token)
    file = next((f for f in turn.files if f["id"] == file_id), None)
    if not file:
        raise HTTPException(404, "File not attached to this turn")
    url = file.get("url_private_download") or file.get("url_private") or ""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "files.slack.com" or parsed.username or parsed.password:
        raise HTTPException(422, "Unsupported Slack file URL")
    if (file.get("size") or 0) > MAX_FILE_BYTES:
        raise HTTPException(413, "Use a repository file or a preview smaller than 20 MiB")
    # Never forward the Slack bearer token to redirects or arbitrary hosts.
    with httpx.stream("GET", url, headers={"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"}, timeout=60) as reply:
        if reply.status_code != 200:
            raise HTTPException(502, "Slack file download failed")
        chunks, size = [], 0
        for chunk in reply.iter_bytes():
            size += len(chunk)
            if size > MAX_FILE_BYTES:
                raise HTTPException(413, "File exceeds 20 MiB")
            chunks.append(chunk)
    return Response(b"".join(chunks), media_type="application/octet-stream")


@router.put("/turns/{turn_id}/artifacts/{artifact_id}")
async def upload_artifact(turn_id: str, artifact_id: str, request: Request,
                          claim_token: str, name: str, db: Session = Depends(get_db)):
    if not re.fullmatch(r"[a-f0-9]{64}", artifact_id):
        raise HTTPException(422, "Artifact ID must be its SHA-256")
    assert_allowed(name)
    active_turn(db, turn_id, claim_token)
    # Release row lock while receiving bytes; revalidate the claim before commit.
    db.rollback()
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_FILE_BYTES:
            raise HTTPException(413, "Upload a preview smaller than 20 MiB")
        chunks.append(chunk)
    content = b"".join(chunks)
    if hashlib.sha256(content).hexdigest() != artifact_id:
        raise HTTPException(422, "Artifact checksum mismatch")
    turn = active_turn(db, turn_id, claim_token)
    key = f"{turn_id}:artifact:{artifact_id}"
    existing = db.query(ConversationDelivery).filter_by(dedupe_key=key).first()
    if existing:
        return {"delivery_id": existing.id, "status": existing.status}
    # turn_id came from a DB row, name is reduced to a filename.
    directory = Path(settings.SLACK_ARTIFACT_DIR) / turn.id
    directory.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w. -]", "_", Path(name).name)[:150] or "artifact"
    path = directory / f"{artifact_id[:12]}-{safe_name}"
    path.write_bytes(content)
    delivery = ConversationDelivery(conversation_id=turn.conversation_id, dedupe_key=key,
                                    kind="file", text=safe_name, file_path=str(path))
    db.add(delivery)
    db.commit()
    return {"delivery_id": delivery.id, "status": delivery.status}
