"""ai_insight_provenance

DATABASE_CONTRACT §4.4 (approved by the user 2026-11-14, REQ-28). Additive: four
nullable provenance columns on ai_insights, no server default and no backfill. A NULL
generated_by marks a row written before provenance existed; such rows are never
served. downgrade drops the four columns and nothing else.

Revision ID: e4a8c2f6b1d3
Revises: d7b2e6f4a913
Create Date: 2026-11-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e4a8c2f6b1d3'
down_revision: Union[str, Sequence[str], None] = 'd7b2e6f4a913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLUMNS = ('generated_by', 'generated_at', 'inputs_as_of', 'is_fallback')


def upgrade() -> None:
    with op.batch_alter_table('ai_insights') as batch:
        batch.add_column(sa.Column('generated_by', sa.String(length=100), nullable=True))
        batch.add_column(sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('inputs_as_of', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('is_fallback', sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('ai_insights') as batch:
        for column in reversed(_COLUMNS):
            batch.drop_column(column)
