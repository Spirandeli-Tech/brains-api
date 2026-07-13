"""add_claude_model_to_runs

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('implementation_runs', sa.Column('claude_model', sa.String(), nullable=True))
    op.add_column('code_review_runs', sa.Column('claude_model', sa.String(), nullable=True))
    op.add_column('address_pr_runs', sa.Column('claude_model', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('address_pr_runs', 'claude_model')
    op.drop_column('code_review_runs', 'claude_model')
    op.drop_column('implementation_runs', 'claude_model')
