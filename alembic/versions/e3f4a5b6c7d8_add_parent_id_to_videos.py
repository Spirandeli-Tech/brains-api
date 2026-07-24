"""add_parent_id_to_videos

The content model is hub-and-spoke: one long episode (8–15min, Sunday) is the
product, and 2–3 cuts plus a podcast derive from it. Without a self-reference
there is no way to count "2–3 cuts per episode", which is the whole point of the
cadence view.

Also normalises `format`: the first cut of this table used `short | video`, which
came from a short-form assumption that the channel plan (labs/docs/series-map.html)
contradicts — the long piece is the product, not the derivative. Existing rows
with format 'video' become 'episode'.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'videos',
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_videos_parent_id',
        'videos',
        'videos',
        ['parent_id'],
        ['id'],
        ondelete='CASCADE',
    )
    op.create_index('ix_videos_parent_id', 'videos', ['parent_id'])

    # 'video' was the old name for the long piece. Nothing used 'podcast' yet.
    op.execute("UPDATE videos SET format = 'episode' WHERE format = 'video'")
    op.alter_column('videos', 'format', server_default='episode')


def downgrade() -> None:
    op.alter_column('videos', 'format', server_default='short')
    op.execute("UPDATE videos SET format = 'video' WHERE format = 'episode'")

    op.drop_index('ix_videos_parent_id', table_name='videos')
    op.drop_constraint('fk_videos_parent_id', 'videos', type_='foreignkey')
    op.drop_column('videos', 'parent_id')
