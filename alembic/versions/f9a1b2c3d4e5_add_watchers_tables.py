"""add_watchers_tables

Revision ID: f9a1b2c3d4e5
Revises: d815abb46c49
Create Date: 2026-07-14 00:00:00.000003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f9a1b2c3d4e5'
down_revision: Union[str, None] = 'd815abb46c49'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'watchers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('connection_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('interval_minutes', sa.Integer(), server_default='10', nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_status', sa.String(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['connection_id'], ['productivity_connections.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_watchers_user_id', 'watchers', ['user_id'])
    op.create_index('ix_watchers_enabled', 'watchers', ['enabled'])

    op.create_table(
        'watcher_sightings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('watcher_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('external_key', sa.String(), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('handled_ref', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['watcher_id'], ['watchers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('watcher_id', 'external_key', name='uq_watcher_sighting_key'),
    )
    op.create_index('ix_watcher_sightings_watcher_id', 'watcher_sightings', ['watcher_id'])


def downgrade() -> None:
    op.drop_index('ix_watcher_sightings_watcher_id', table_name='watcher_sightings')
    op.drop_table('watcher_sightings')
    op.drop_index('ix_watchers_enabled', table_name='watchers')
    op.drop_index('ix_watchers_user_id', table_name='watchers')
    op.drop_table('watchers')
