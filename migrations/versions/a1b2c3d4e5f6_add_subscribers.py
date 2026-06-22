"""add subscribers table

Revision ID: a1b2c3d4e5f6
Revises: ef2d0c714fff
Create Date: 2026-06-23 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'ef2d0c714fff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'subscribers',
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('first_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('subscription_until', sa.DateTime(), nullable=True),
        sa.Column('is_recurring', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('last_charge_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('telegram_id'),
    )
    op.create_index('ix_subscribers_subscription_until', 'subscribers', ['subscription_until'])


def downgrade() -> None:
    op.drop_index('ix_subscribers_subscription_until', table_name='subscribers')
    op.drop_table('subscribers')
