"""add empresa agent tables (agents, agent_tasks, agent_messages)

Revision ID: e7a9b2c4d6f8
Revises: b8c9d0e1f2a3
Create Date: 2026-08-18

Módulo Empresa (fábrica de SaaS): identidade dos agentes, fila de execução e
feed de mensagens. Escrita à mão — o autogenerate do projeto está cego (ver
alembic/env.py). Seed dos agentes NÃO mora aqui: a fonte de verdade é
fabrica/agents.yaml, aplicada via fabrica/seed.py → POST /empresa/runner/seed-agents.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7a9b2c4d6f8"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("human_name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("area", sa.String(), nullable=False),
        sa.Column("reports_to", sa.String(), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("skills", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agents_slug", "agents", ["slug"], unique=True)
    op.create_index("ix_agents_enabled", "agents", ["enabled"])

    op.create_table(
        "agent_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_slug", sa.String(), nullable=False),
        sa.Column("skill", sa.String(), nullable=False),
        sa.Column("trigger", sa.String(), server_default="manual", nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("status", sa.String(), server_default="queued", nullable=False),
        sa.Column("claimed_by", sa.String(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_tasks_status", "agent_tasks", ["status"])
    op.create_index("ix_agent_tasks_agent_slug", "agent_tasks", ["agent_slug"])

    op.create_table(
        "agent_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_agent", sa.String(), nullable=False),
        sa.Column("to_agent", sa.String(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("artifact_url", sa.String(), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("slack_ts", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["agent_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_messages_created_at", "agent_messages", ["created_at"])
    op.create_index("ix_agent_messages_to_agent", "agent_messages", ["to_agent"])


def downgrade() -> None:
    op.drop_index("ix_agent_messages_to_agent", table_name="agent_messages")
    op.drop_index("ix_agent_messages_created_at", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_index("ix_agent_tasks_agent_slug", table_name="agent_tasks")
    op.drop_index("ix_agent_tasks_status", table_name="agent_tasks")
    op.drop_table("agent_tasks")
    op.drop_index("ix_agents_enabled", table_name="agents")
    op.drop_index("ix_agents_slug", table_name="agents")
    op.drop_table("agents")
