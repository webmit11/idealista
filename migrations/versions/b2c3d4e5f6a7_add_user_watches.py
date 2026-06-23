"""add per-user watches table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-23 01:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_watches',
        sa.Column('telegram_id', sa.BigInteger(), nullable=False),
        sa.Column('property_id', sa.Integer(), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('note', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['property_id'], ['properties.id']),
        sa.PrimaryKeyConstraint('telegram_id', 'property_id'),
    )
    op.create_index('ix_user_watches_telegram_id', 'user_watches', ['telegram_id'])


def downgrade() -> None:
    op.drop_index('ix_user_watches_telegram_id', table_name='user_watches')
    op.drop_table('user_watches')
