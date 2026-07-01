"""add_manual_trigger_to_automation_runs

Revision ID: c9d0e1f2a3b4
Revises: b1c2d3e4f5a6
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'automation_runs',
        sa.Column('is_manual', sa.Boolean(), server_default='false', nullable=False),
    )
    op.drop_constraint('uq_automation_run_schedule', 'automation_runs', type_='unique')
    op.create_index(
        'uq_automation_run_schedule_auto',
        'automation_runs',
        ['automation_id', 'scheduled_for'],
        unique=True,
        postgresql_where=sa.text('NOT is_manual'),
    )


def downgrade() -> None:
    op.drop_index('uq_automation_run_schedule_auto', table_name='automation_runs')
    op.create_unique_constraint(
        'uq_automation_run_schedule', 'automation_runs', ['automation_id', 'scheduled_for']
    )
    op.drop_column('automation_runs', 'is_manual')
