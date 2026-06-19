"""add_implementation_tables

Revision ID: a1c2e3f4d5b6
Revises: f1a2b3c4d5e6
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1c2e3f4d5b6'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'implementation_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('ticket_url', sa.String(), nullable=False),
        sa.Column('ticket_key', sa.String(), nullable=True),
        sa.Column('ticket_summary', sa.String(), nullable=True),
        sa.Column('status', sa.String(), server_default='queued', nullable=False),
        sa.Column('worktree_path', sa.String(), nullable=True),
        sa.Column('branch', sa.String(), nullable=True),
        sa.Column('pr_url', sa.String(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('claimed_by', sa.String(), nullable=True),
        sa.Column('claimed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'],),
        sa.ForeignKeyConstraint(
            ['connection_id'], ['productivity_connections.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_impl_runs_user', 'implementation_runs', ['created_by_user_id'])
    op.create_index('ix_impl_runs_status', 'implementation_runs', ['status'])
    op.create_index('ix_impl_runs_connection', 'implementation_runs', ['connection_id'])

    op.create_table(
        'implementation_steps',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sensitive', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('log', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['implementation_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_impl_steps_run', 'implementation_steps', ['run_id'])


def downgrade() -> None:
    op.drop_index('ix_impl_steps_run', table_name='implementation_steps')
    op.drop_table('implementation_steps')
    op.drop_index('ix_impl_runs_connection', table_name='implementation_runs')
    op.drop_index('ix_impl_runs_status', table_name='implementation_runs')
    op.drop_index('ix_impl_runs_user', table_name='implementation_runs')
    op.drop_table('implementation_runs')
