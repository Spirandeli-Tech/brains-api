"""merge_heads

Revision ID: b26158006a0f
Revises: f3a4b5c6d7e8, 9c2d3e4f5a6b
Create Date: 2026-07-14 00:00:00.000001

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = 'b26158006a0f'
down_revision: Union[str, tuple[str, ...], None] = ('f3a4b5c6d7e8', '9c2d3e4f5a6b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
