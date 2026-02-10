"""add_bank_accounts_invoice_services

Revision ID: c3a7f1b2d4e6
Revises: b01cb9209b95
Create Date: 2026-02-10 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3a7f1b2d4e6'
down_revision: Union[str, None] = 'b01cb9209b95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create bank_accounts table
    op.create_table('bank_accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_by_user_id', sa.UUID(), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('beneficiary_full_name', sa.String(), nullable=False),
        sa.Column('beneficiary_full_address', sa.String(), nullable=True),
        sa.Column('beneficiary_account_number', sa.String(), nullable=False),
        sa.Column('swift_code', sa.String(), nullable=False),
        sa.Column('bank_name', sa.String(), nullable=True),
        sa.Column('bank_address', sa.String(), nullable=True),
        sa.Column('intermediary_swift_code', sa.String(), nullable=True),
        sa.Column('intermediary_bank_name', sa.String(), nullable=True),
        sa.Column('intermediary_bank_address', sa.String(), nullable=True),
        sa.Column('intermediary_account_number', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('created_by_user_id', 'label', name='uq_bank_account_user_label'),
    )
    op.create_index('ix_bank_accounts_created_by_user_id', 'bank_accounts', ['created_by_user_id'], unique=False)

    # 2. Add new columns to invoices
    op.add_column('invoices', sa.Column('bank_account_id', sa.UUID(), nullable=True))
    op.add_column('invoices', sa.Column('total_amount', sa.Numeric(precision=12, scale=2), server_default='0', nullable=False))
    op.create_foreign_key('fk_invoices_bank_account_id', 'invoices', 'bank_accounts', ['bank_account_id'], ['id'])
    op.create_index('ix_invoices_bank_account', 'invoices', ['bank_account_id'], unique=False)

    # 3. Create invoice_services table
    op.create_table('invoice_services',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_by_user_id', sa.UUID(), nullable=False),
        sa.Column('invoice_id', sa.UUID(), nullable=False),
        sa.Column('service_title', sa.String(), nullable=False),
        sa.Column('service_description', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_invoice_services_created_by_user_id', 'invoice_services', ['created_by_user_id'], unique=False)
    op.create_index('ix_invoice_services_invoice_id', 'invoice_services', ['invoice_id'], unique=False)

    # 4. Backfill: migrate existing single-service invoices to invoice_services
    op.execute("""
        INSERT INTO invoice_services (id, created_by_user_id, invoice_id, service_title, service_description, amount, sort_order, created_at, updated_at)
        SELECT gen_random_uuid(), created_by_user_id, id, service_title, COALESCE(service_description, ''), amount_total, 0, created_at, updated_at
        FROM invoices
        WHERE service_title IS NOT NULL
    """)

    # 5. Set total_amount from existing amount_total
    op.execute("""
        UPDATE invoices SET total_amount = COALESCE(amount_total, 0)
    """)

    # 6. Make old columns nullable (deprecate)
    op.alter_column('invoices', 'service_title', existing_type=sa.String(), nullable=True)
    op.alter_column('invoices', 'service_description', existing_type=sa.Text(), nullable=True)
    op.alter_column('invoices', 'amount_total', existing_type=sa.Numeric(precision=12, scale=2), nullable=True)


def downgrade() -> None:
    # Restore old columns to not-null
    op.alter_column('invoices', 'amount_total', existing_type=sa.Numeric(precision=12, scale=2), nullable=False)
    op.alter_column('invoices', 'service_description', existing_type=sa.Text(), nullable=False)
    op.alter_column('invoices', 'service_title', existing_type=sa.String(), nullable=False)

    # Drop invoice_services table
    op.drop_index('ix_invoice_services_invoice_id', table_name='invoice_services')
    op.drop_index('ix_invoice_services_created_by_user_id', table_name='invoice_services')
    op.drop_table('invoice_services')

    # Remove new columns from invoices
    op.drop_index('ix_invoices_bank_account', table_name='invoices')
    op.drop_constraint('fk_invoices_bank_account_id', 'invoices', type_='foreignkey')
    op.drop_column('invoices', 'total_amount')
    op.drop_column('invoices', 'bank_account_id')

    # Drop bank_accounts table
    op.drop_index('ix_bank_accounts_created_by_user_id', table_name='bank_accounts')
    op.drop_table('bank_accounts')
