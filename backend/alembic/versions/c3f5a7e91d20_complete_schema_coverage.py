"""complete_schema_coverage

DATABASE_CONTRACT §4.2 (REQ-16). After this revision a database built only from
migrations matches models.py, so production no longer relies on create_all:

- the four market-data cache tables that create_all built at startup
  (stock_data, turkish_gold, exchange_rates, ai_insights), exactly as the models
  declare them; Python-side defaults stay Python-side
- ix_auth_tokens_user_id, declared in the model but missing from 8c15c00878ff
- uq_instruments_provider_symbol, so a provider spelling names one instrument

Additive only. downgrade drops exactly these objects in reverse order.

Revision ID: c3f5a7e91d20
Revises: b2e4d8a31c55
Create Date: 2026-11-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f5a7e91d20'
down_revision: Union[str, Sequence[str], None] = 'b2e4d8a31c55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('ai_insights',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('insight_type', sa.String(length=20), nullable=True),
    sa.Column('symbol', sa.String(length=20), nullable=True),
    sa.Column('insight_text', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('exchange_rates',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('pair', sa.String(length=10), nullable=False),
    sa.Column('display_name', sa.String(length=50), nullable=True),
    sa.Column('buying', sa.Float(), nullable=True),
    sa.Column('selling', sa.Float(), nullable=True),
    sa.Column('change_pct', sa.Float(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('pair')
    )
    op.create_table('stock_data',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('symbol', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=True),
    sa.Column('price', sa.Float(), nullable=True),
    sa.Column('change_pct', sa.Float(), nullable=True),
    sa.Column('volume', sa.Float(), nullable=True),
    sa.Column('day_high', sa.Float(), nullable=True),
    sa.Column('day_low', sa.Float(), nullable=True),
    sa.Column('open_price', sa.Float(), nullable=True),
    sa.Column('previous_close', sa.Float(), nullable=True),
    sa.Column('bid', sa.Float(), nullable=True),
    sa.Column('ask', sa.Float(), nullable=True),
    sa.Column('rsi', sa.Float(), nullable=True),
    sa.Column('ma_20', sa.Float(), nullable=True),
    sa.Column('volatility', sa.String(length=10), nullable=True),
    sa.Column('currency', sa.String(length=5), nullable=True),
    sa.Column('market_type', sa.String(length=20), nullable=True),
    sa.Column('prediction', sa.String(length=500), nullable=True),
    sa.Column('reason', sa.String(length=500), nullable=True),
    sa.Column('is_favorable', sa.Boolean(), nullable=True),
    sa.Column('is_buyable', sa.Boolean(), nullable=True),
    sa.Column('market_cap', sa.Float(), nullable=True),
    sa.Column('extra_data', sa.JSON(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_stock_market_type', 'stock_data', ['market_type'], unique=False)
    op.create_index('idx_stock_symbol_updated', 'stock_data', ['symbol', 'updated_at'], unique=False)
    op.create_index(op.f('ix_stock_data_symbol'), 'stock_data', ['symbol'], unique=False)
    op.create_table('turkish_gold',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('gold_type', sa.String(length=50), nullable=False),
    sa.Column('display_name', sa.String(length=100), nullable=True),
    sa.Column('buying_price', sa.Float(), nullable=True),
    sa.Column('selling_price', sa.Float(), nullable=True),
    sa.Column('change_pct', sa.Float(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('gold_type')
    )
    op.create_index(op.f('ix_auth_tokens_user_id'), 'auth_tokens', ['user_id'], unique=False)
    # batch: SQLite cannot add a constraint to an existing table with ALTER.
    with op.batch_alter_table('instruments') as batch_op:
        batch_op.create_unique_constraint('uq_instruments_provider_symbol', ['provider_symbol'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('instruments') as batch_op:
        batch_op.drop_constraint('uq_instruments_provider_symbol', type_='unique')
    op.drop_index(op.f('ix_auth_tokens_user_id'), table_name='auth_tokens')
    op.drop_table('turkish_gold')
    op.drop_index(op.f('ix_stock_data_symbol'), table_name='stock_data')
    op.drop_index('idx_stock_symbol_updated', table_name='stock_data')
    op.drop_index('idx_stock_market_type', table_name='stock_data')
    op.drop_table('stock_data')
    op.drop_table('exchange_rates')
    op.drop_table('ai_insights')
