"""rename_work_dir_to_repo_name_on_automations

Revision ID: 3b4c5d6e7f8a
Revises: 2a3b4c5d6e7f
Create Date: 2026-07-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = '3b4c5d6e7f8a'
down_revision: Union[str, None] = '2a3b4c5d6e7f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('automations', 'work_dir', new_column_name='repo_name')


def downgrade() -> None:
    op.alter_column('automations', 'repo_name', new_column_name='work_dir')
