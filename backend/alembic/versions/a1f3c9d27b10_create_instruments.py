"""create_instruments

M1 in DATABASE_CONTRACT §4. Additive: creates one new table, touches nothing else.
Rows are loaded by services.instrument_service.sync_instruments, not by this migration.

Revision ID: a1f3c9d27b10
Revises: 8c15c00878ff
Create Date: 2026-11-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1f3c9d27b10'
down_revision: Union[str, Sequence[str], None] = '8c15c00878ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'instruments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(length=20), nullable=False),
        sa.Column('exchange', sa.String(length=10), nullable=False),
        sa.Column('provider_symbol', sa.String(length=30), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=True),
        sa.Column('currency', sa.CHAR(length=3), nullable=False),
        sa.Column('asset_class', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol', 'exchange', name='uq_instruments_symbol_exchange'),
    )


def downgrade() -> None:
    op.drop_table('instruments')
