import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.db import Base


class AgentTask(Base):
    """Uma execução enfileirada de skill por um agente da empresa — a fila da fábrica.

    O runner faz claim (mesmo padrão FOR UPDATE SKIP LOCKED do code_review), com
    a trava de identidade: no máximo 1 task `running` por agente — paralelismo
    vem de agentes diferentes, nunca do mesmo (escala-se contratando outro
    agente, não clonando). `trigger` diz quem acordou a task: message (o
    dispatcher), cron (Automation/ritual), watcher (evento) ou manual. `payload`
    carrega o contexto (a mensagem, o ticket) que a skill recebe.
    """

    __tablename__ = "agent_tasks"

    __table_args__ = (
        Index("ix_agent_tasks_status", "status"),
        Index("ix_agent_tasks_agent_slug", "agent_slug"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_slug = Column(String, nullable=False)
    skill = Column(String, nullable=False)
    # message | cron | watcher | manual
    trigger = Column(String, nullable=False, default="manual", server_default="manual")
    payload = Column(JSONB, nullable=False, default=dict, server_default="{}")
    # queued | running | done | failed
    status = Column(String, nullable=False, default="queued", server_default="queued")
    claimed_by = Column(String, nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    # transcript da execução, atualizado ao vivo pelo runner (streaming na UI)
    log = Column(Text, nullable=True)
    cost_usd = Column(Numeric(10, 4), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
