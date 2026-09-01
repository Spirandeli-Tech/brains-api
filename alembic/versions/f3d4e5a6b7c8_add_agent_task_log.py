"""add log column to agent_tasks (transcript ao vivo da execução)

Revision ID: f3d4e5a6b7c8
Revises: e7a9b2c4d6f8
Create Date: 2026-08-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3d4e5a6b7c8"
down_revision: Union[str, None] = "e7a9b2c4d6f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agent_tasks", sa.Column("log", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_tasks", "log")
