"""add_photo_url_and_user_preferences

Revision ID: c2d3e4f5a6b7
Revises: aa9ec6fdc43d
Create Date: 2026-02-13 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'aa9ec6fdc43d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add photo_url to users table
    op.add_column('users', sa.Column('photo_url', sa.String(), nullable=True))

    # Create user_preferences table
    op.create_table('user_preferences',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('report_theme_color', sa.String(), nullable=True, server_default='#1677ff'),
        sa.Column('report_header_image_url', sa.String(), nullable=True),
        sa.Column('default_currency', sa.String(), nullable=True, server_default='USD'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_index('ix_user_preferences_user_id', 'user_preferences', ['user_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_user_preferences_user_id', table_name='user_preferences')
    op.drop_table('user_preferences')
    op.drop_column('users', 'photo_url')
