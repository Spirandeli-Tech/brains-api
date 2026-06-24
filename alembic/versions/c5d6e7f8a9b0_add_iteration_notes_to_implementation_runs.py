"""add iteration_notes to implementation_runs

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-06-22 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "implementation_runs",
        sa.Column("iteration_notes", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("implementation_runs", "iteration_notes")
