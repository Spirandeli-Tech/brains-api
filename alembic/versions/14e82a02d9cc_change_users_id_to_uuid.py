"""change_users_id_to_uuid

Revision ID: 14e82a02d9cc
Revises: 69fc5227ffbc
Create Date: 2026-02-10 17:12:45.744516

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '14e82a02d9cc'
down_revision: Union[str, None] = '69fc5227ffbc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index('ix_users_id', table_name='users')
    op.drop_column('users', 'id')
    op.add_column('users', sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False))
    op.create_primary_key('users_pkey', 'users', ['id'])


def downgrade() -> None:
    op.drop_constraint('users_pkey', 'users', type_='primary')
    op.drop_column('users', 'id')
    op.add_column('users', sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False))
    op.create_primary_key('users_pkey', 'users', ['id'])
    op.create_index('ix_users_id', 'users', ['id'], unique=False)
