"""add saved_filters table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-23 03:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'saved_filters',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('telegram_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('criteria_json', sa.JSON(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_notified_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_saved_filters_telegram_id', 'saved_filters', ['telegram_id'])


def downgrade() -> None:
    op.drop_index('ix_saved_filters_telegram_id', table_name='saved_filters')
    op.drop_table('saved_filters')
