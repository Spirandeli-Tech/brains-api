"""add_automations

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-06-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd6e7f8a9b0c1'
down_revision: Union[str, None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'automations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('skill', sa.String(), nullable=False),
        sa.Column('connection_name', sa.String(), nullable=True),
        sa.Column('work_dir', sa.String(), nullable=True),
        sa.Column('frequency', sa.String(), nullable=False),
        sa.Column('day_of_week', sa.Integer(), nullable=True),
        sa.Column('day_of_month', sa.Integer(), nullable=True),
        sa.Column('time_of_day', sa.Time(), server_default='08:00:00', nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'],),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_automations_user_id', 'automations', ['user_id'])
    op.create_index('ix_automations_enabled', 'automations', ['enabled'])

    op.create_table(
        'automation_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('automation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scheduled_for', sa.Date(), nullable=False),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('log', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('claimed_by', sa.String(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['automation_id'], ['automations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('automation_id', 'scheduled_for', name='uq_automation_run_schedule'),
    )
    op.create_index('ix_automation_runs_automation_id', 'automation_runs', ['automation_id'])
    op.create_index('ix_automation_runs_status', 'automation_runs', ['status'])
    op.create_index('ix_automation_runs_scheduled_for', 'automation_runs', ['scheduled_for'])


def downgrade() -> None:
    op.drop_index('ix_automation_runs_scheduled_for', table_name='automation_runs')
    op.drop_index('ix_automation_runs_status', table_name='automation_runs')
    op.drop_index('ix_automation_runs_automation_id', table_name='automation_runs')
    op.drop_table('automation_runs')
    op.drop_index('ix_automations_enabled', table_name='automations')
    op.drop_index('ix_automations_user_id', table_name='automations')
    op.drop_table('automations')
