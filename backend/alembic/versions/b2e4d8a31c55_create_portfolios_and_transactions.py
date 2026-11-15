"""create_portfolios_and_transactions

M2 in DATABASE_CONTRACT §4. Additive: creates two new tables, touches nothing else.

Revision ID: b2e4d8a31c55
Revises: a1f3c9d27b10
Create Date: 2026-11-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2e4d8a31c55'
down_revision: Union[str, Sequence[str], None] = 'a1f3c9d27b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# SQLite only auto-increments an INTEGER primary key; Postgres gets BIGINT.
_big_id = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')


def upgrade() -> None:
    op.create_table(
        'portfolios',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('base_currency', sa.CHAR(length=3), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("kind IN ('real', 'paper')", name='ck_portfolios_kind'),
    )
    op.create_index('ix_portfolios_user_id', 'portfolios', ['user_id'])
    op.create_index(
        'uq_portfolios_user_name_active', 'portfolios', ['user_id', 'name'], unique=True,
        postgresql_where=sa.text('archived_at IS NULL'),
        sqlite_where=sa.text('archived_at IS NULL'),
    )

    op.create_table(
        'transactions',
        sa.Column('id', _big_id, autoincrement=True, nullable=False),
        sa.Column('portfolio_id', sa.Integer(), nullable=False),
        sa.Column('instrument_id', sa.Integer(), nullable=True),
        sa.Column('type', sa.String(length=12), nullable=False),
        sa.Column('quantity', sa.Numeric(24, 8), nullable=False),
        sa.Column('price', sa.Numeric(20, 6), nullable=True),
        sa.Column('fee', sa.Numeric(20, 6), server_default=sa.text('0'), nullable=False),
        sa.Column('currency', sa.CHAR(length=3), nullable=False),
        sa.Column('fx_rate_to_base', sa.Numeric(20, 8), nullable=True),
        sa.Column('trade_date', sa.Date(), nullable=False),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('note', sa.String(length=500), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('voids_transaction_id', _big_id, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['voids_transaction_id'], ['transactions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "type IN ('BUY', 'SELL', 'DIVIDEND', 'FEE', 'DEPOSIT', 'WITHDRAWAL', 'SPLIT')",
            name='ck_transactions_type',
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'import', 'paper_fill')", name='ck_transactions_source'
        ),
        sa.CheckConstraint('quantity >= 0', name='ck_transactions_quantity_non_negative'),
        sa.CheckConstraint('fee >= 0', name='ck_transactions_fee_non_negative'),
        sa.CheckConstraint('price IS NULL OR price >= 0', name='ck_transactions_price_non_negative'),
        sa.CheckConstraint(
            'fx_rate_to_base IS NULL OR fx_rate_to_base > 0', name='ck_transactions_fx_rate_positive'
        ),
    )
    op.create_index(
        'ix_transactions_portfolio_date_id', 'transactions', ['portfolio_id', 'trade_date', 'id']
    )
    op.create_index('ix_transactions_instrument_id', 'transactions', ['instrument_id'])
    op.create_index(
        'uq_transactions_voids_transaction_id', 'transactions', ['voids_transaction_id'], unique=True
    )


def downgrade() -> None:
    op.drop_table('transactions')
    op.drop_table('portfolios')
