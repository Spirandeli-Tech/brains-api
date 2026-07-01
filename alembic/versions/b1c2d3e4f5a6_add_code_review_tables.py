"""add_code_review_tables

Revision ID: b1c2d3e4f5a6
Revises: b7c8d9e0f1a2
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'code_review_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('pr_url', sa.String(), nullable=False),
        sa.Column('pr_number', sa.String(), nullable=True),
        sa.Column('repo_name', sa.String(), nullable=True),
        sa.Column('ticket_key', sa.String(), nullable=True),
        sa.Column('instructions', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), server_default='queued', nullable=False),
        sa.Column('review_action', sa.String(), nullable=True),
        sa.Column('review_plan', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
    op.create_index('ix_cr_runs_user', 'code_review_runs', ['created_by_user_id'])
    op.create_index('ix_cr_runs_status', 'code_review_runs', ['status'])
    op.create_index('ix_cr_runs_connection', 'code_review_runs', ['connection_id'])

    op.create_table(
        'code_review_steps',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sensitive', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('approved', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('log', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['code_review_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cr_steps_run', 'code_review_steps', ['run_id'])


def downgrade() -> None:
    op.drop_index('ix_cr_steps_run', table_name='code_review_steps')
    op.drop_table('code_review_steps')
    op.drop_index('ix_cr_runs_connection', table_name='code_review_runs')
    op.drop_index('ix_cr_runs_status', table_name='code_review_runs')
    op.drop_index('ix_cr_runs_user', table_name='code_review_runs')
    op.drop_table('code_review_runs')
