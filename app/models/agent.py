import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.db import Base


class Agent(Base):
    """Um membro da empresa de agentes (fábrica de SaaS) — identidade, não execução.

    A fonte de verdade versionada é `fabrica/agents.yaml` (brains-root); esta
    tabela é o seed dela para a UI (organograma vivo) e para o dispatcher.
    `reports_to` guarda o slug do superior (cadeia de comando); "investidor" é
    um participante externo, não uma linha aqui. Execução fica em AgentTask;
    conversa fica em AgentMessage — o estado de um agente (rodando/ocioso) é
    derivado das tasks, nunca armazenado aqui.
    """

    __tablename__ = "agents"

    __table_args__ = (
        Index("ix_agents_slug", "slug", unique=True),
        Index("ix_agents_enabled", "enabled"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String, nullable=False)
    human_name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    area = Column(String, nullable=False)
    # slug do superior na cadeia de comando; "investidor" para o CEO
    reports_to = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    # nomes das skills que este agente executa (fabrica/.claude/skills/)
    skills = Column(JSONB, nullable=False, default=list, server_default="[]")
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
