"""add_user_roles_table_and_role_id_to_users

Revision ID: e4690b7018fb
Revises: 14e82a02d9cc
Create Date: 2026-02-10 17:41:22.505976

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import uuid


# revision identifiers, used by Alembic.
revision: str = 'e4690b7018fb'
down_revision: Union[str, None] = '14e82a02d9cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN_ROLE_ID = uuid.uuid4()
CLIENT_ROLE_ID = uuid.uuid4()


def upgrade() -> None:
    user_roles_table = op.create_table(
        'user_roles',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.bulk_insert(user_roles_table, [
        {'id': ADMIN_ROLE_ID, 'name': 'ADMIN', 'description': 'Administrator with full access'},
        {'id': CLIENT_ROLE_ID, 'name': 'CLIENT', 'description': 'Standard client user'},
    ])

    op.add_column('users', sa.Column('role_id', sa.UUID(), nullable=True))

    op.execute(f"UPDATE users SET role_id = '{CLIENT_ROLE_ID}'")

    op.create_foreign_key('fk_users_role_id', 'users', 'user_roles', ['role_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_users_role_id', 'users', type_='foreignkey')
    op.drop_column('users', 'role_id')
    op.drop_table('user_roles')
