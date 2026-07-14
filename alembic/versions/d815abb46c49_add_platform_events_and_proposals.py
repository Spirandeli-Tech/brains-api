"""add_platform_events_and_proposals

Revision ID: d815abb46c49
Revises: b26158006a0f
Create Date: 2026-07-14 00:00:00.000002

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd815abb46c49'
down_revision: Union[str, None] = 'b26158006a0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'platform_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('event_type', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('connection_name', sa.String(), nullable=True),
        sa.Column('ref_kind', sa.String(), nullable=True),
        sa.Column('ref_id', sa.String(), nullable=True),
        sa.Column('url_path', sa.String(), nullable=True),
        sa.Column('seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_platform_events_occurred_at', 'platform_events', ['occurred_at']
    )
    op.create_index('ix_platform_events_seen_at', 'platform_events', ['seen_at'])

    op.create_table(
        'proposals',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('action_kind', sa.String(), nullable=False),
        sa.Column('action_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('result_ref', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_proposals_status', 'proposals', ['status'])


def downgrade() -> None:
    op.drop_index('ix_proposals_status', table_name='proposals')
    op.drop_table('proposals')
    op.drop_index('ix_platform_events_seen_at', table_name='platform_events')
    op.drop_index('ix_platform_events_occurred_at', table_name='platform_events')
    op.drop_table('platform_events')
