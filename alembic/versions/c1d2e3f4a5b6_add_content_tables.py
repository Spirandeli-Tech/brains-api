"""add_content_tables

Ideas, videos and versioned video scripts — the publication calendar that
replaces the two Google Sheet tabs (`Banco` and `Roteiros`).

Revision ID: c1d2e3f4a5b6
Revises: b7c1d2e3f4a5
Create Date: 2026-07-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'b7c1d2e3f4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ideas',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('format', sa.String(), server_default='short', nullable=False),
        sa.Column('type', sa.String(), nullable=True),
        sa.Column('priority', sa.String(), server_default='media', nullable=False),
        sa.Column('status', sa.String(), server_default='idea', nullable=False),
        sa.Column('hook', sa.Text(), nullable=True),
        sa.Column('why_now', sa.Text(), nullable=True),
        sa.Column('visual_refs', sa.Text(), nullable=True),
        sa.Column('trustworthy', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('fact_check', sa.Text(), nullable=True),
        sa.Column('theme_filter', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('source', sa.String(), server_default='manual', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ideas_user_id', 'ideas', ['user_id'])
    op.create_index('ix_ideas_status', 'ideas', ['status'])
    op.create_index('ix_ideas_slug', 'ideas', ['slug'])

    op.create_table(
        'videos',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('idea_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=True),
        sa.Column('keyword', sa.String(), nullable=True),
        sa.Column('format', sa.String(), server_default='short', nullable=False),
        sa.Column('series', sa.String(), nullable=True),
        sa.Column('episode_number', sa.Integer(), nullable=True),
        sa.Column('publish_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(), server_default='idea', nullable=False),
        sa.Column('thumb_url', sa.Text(), nullable=True),
        sa.Column('youtube_url', sa.Text(), nullable=True),
        sa.Column('ctr_48h', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('retention_48h', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('learning', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['idea_id'], ['ideas.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_videos_user_id', 'videos', ['user_id'])
    op.create_index('ix_videos_status', 'videos', ['status'])
    op.create_index('ix_videos_publish_date', 'videos', ['publish_date'])
    op.create_index('ix_videos_idea_id', 'videos', ['idea_id'])

    op.create_table(
        'video_scripts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('video_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('titles', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('caption', sa.Text(), nullable=True),
        sa.Column('hashtags', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('cover', sa.Text(), nullable=True),
        sa.Column('facts_used', sa.Text(), nullable=True),
        sa.Column('growth_checklist', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('short_cuts', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('persona', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('video_id', 'version', name='uq_video_scripts_video_id_version'),
    )
    op.create_index('ix_video_scripts_video_id', 'video_scripts', ['video_id'])


def downgrade() -> None:
    op.drop_index('ix_video_scripts_video_id', table_name='video_scripts')
    op.drop_table('video_scripts')

    op.drop_index('ix_videos_idea_id', table_name='videos')
    op.drop_index('ix_videos_publish_date', table_name='videos')
    op.drop_index('ix_videos_status', table_name='videos')
    op.drop_index('ix_videos_user_id', table_name='videos')
    op.drop_table('videos')

    op.drop_index('ix_ideas_slug', table_name='ideas')
    op.drop_index('ix_ideas_status', table_name='ideas')
    op.drop_index('ix_ideas_user_id', table_name='ideas')
    op.drop_table('ideas')
