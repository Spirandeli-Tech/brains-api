"""Durable Slack threads, ordered agent turns and delivery outbox."""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.core.db import Base


def new_id():
    return str(uuid.uuid4())


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("workspace_id", "app_id", "channel_id", "thread_ts"),)

    id = Column(String, primary_key=True, default=new_id)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    workspace_id = Column(String, nullable=False)
    app_id = Column(String, nullable=False)
    channel_id = Column(String, nullable=False)
    thread_ts = Column(String, nullable=False)
    session_id = Column(String, nullable=True)
    session_host = Column(String, nullable=True)
    session_cwd = Column(String, nullable=True)
    next_sequence = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"
    __table_args__ = (UniqueConstraint("conversation_id", "sequence"),
                      UniqueConstraint("conversation_id", "message_ts"))

    id = Column(String, primary_key=True, default=new_id)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    event_id = Column(String, nullable=False, unique=True)
    message_ts = Column(String, nullable=False)
    sequence = Column(Integer, nullable=False)
    prompt = Column(Text, nullable=False)
    files = Column(JSON, nullable=False, default=list)
    status = Column(String, nullable=False, default="queued", index=True)
    response = Column(Text, nullable=True)
    progress = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    cost_usd = Column(String, nullable=True)
    runner_id = Column(String, nullable=True)
    claim_token = Column(String, nullable=True)
    lease_until = Column(DateTime, nullable=True)
    cancel_requested = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


class ConversationDelivery(Base):
    __tablename__ = "conversation_deliveries"
    id = Column(String, primary_key=True, default=new_id)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False)
    dedupe_key = Column(String, nullable=False, unique=True)
    kind = Column(String, nullable=False, default="text")
    text = Column(Text, nullable=False)
    file_path = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    slack_ts = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
