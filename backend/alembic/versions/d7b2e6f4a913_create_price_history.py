"""create_price_history

DATABASE_CONTRACT §4.3 (approved by the user 2026-11-12, REQ-26). Additive: one new
table of real end-of-day bars per instrument. downgrade drops it and nothing else.

Revision ID: d7b2e6f4a913
Revises: c3f5a7e91d20
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7b2e6f4a913'
down_revision: Union[str, Sequence[str], None] = 'c3f5a7e91d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# SQLite only auto-increments an INTEGER primary key; Postgres gets BIGINT.
_big_id = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')

# Kept in step with models.PRICE_HISTORY_PRICE_CHECK; migrations do not import models.
_PRICE_CHECK = (
    "close > 0"
    " AND (open IS NULL OR open > 0)"
    " AND (high IS NULL OR high > 0)"
    " AND (low IS NULL OR low > 0)"
    " AND (volume IS NULL OR volume >= 0)"
    " AND (high IS NULL OR low IS NULL OR high >= low)"
)


def upgrade() -> None:
    op.create_table(
        'price_history',
        sa.Column('id', _big_id, autoincrement=True, nullable=False),
        sa.Column('instrument_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('open', sa.Numeric(20, 6), nullable=True),
        sa.Column('high', sa.Numeric(20, 6), nullable=True),
        sa.Column('low', sa.Numeric(20, 6), nullable=True),
        sa.Column('close', sa.Numeric(20, 6), nullable=False),
        sa.Column('volume', sa.Numeric(24, 2), nullable=True),
        sa.Column('currency', sa.CHAR(length=3), nullable=False),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('fetched_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instrument_id', 'date', name='uq_price_history_instrument_date'),
        sa.CheckConstraint(_PRICE_CHECK, name='ck_price_history_prices'),
    )


def downgrade() -> None:
    op.drop_table('price_history')
