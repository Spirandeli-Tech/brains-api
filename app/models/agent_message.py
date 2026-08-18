import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.db import Base


class AgentMessage(Base):
    """Uma mensagem entre membros da empresa de agentes — o feed da fábrica.

    `from_agent`/`to_agent` são slugs de Agent, com dois participantes especiais:
    "investidor" (o humano — só conversa com o CEO, protocolo do canal único) e
    None em `to_agent` para informes de sistema/broadcast. Mensagem endereçada e
    acionável vira uma AgentTask (dispatcher em empresa_service.create_message)
    e aponta pra ela via `task_id`. `slack_ts` guarda o timestamp do espelho no
    Slack quando o envio deu certo.
    """

    __tablename__ = "agent_messages"

    __table_args__ = (
        Index("ix_agent_messages_created_at", "created_at"),
        Index("ix_agent_messages_to_agent", "to_agent"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_agent = Column(String, nullable=False)
    to_agent = Column(String, nullable=True)
    body = Column(Text, nullable=False)
    # link pro artefato citado (página Confluence, ticket Jira, PR)
    artifact_url = Column(String, nullable=True)
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    slack_ts = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
