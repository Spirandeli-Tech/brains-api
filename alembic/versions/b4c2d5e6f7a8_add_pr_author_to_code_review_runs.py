"""add_pr_author_to_code_review_runs

Revision ID: b4c2d5e6f7a8
Revises: a3b1c2d4e5f6
Create Date: 2026-07-15 00:00:00.000001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b4c2d5e6f7a8'
down_revision: Union[str, None] = 'a3b1c2d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'code_review_runs',
        sa.Column('pr_author', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('code_review_runs', 'pr_author')
