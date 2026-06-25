"""web storefront lead fields: source/email/budget/timeline/intent + nullable telegram_id

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-06-25 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('leads', sa.Column('source', sa.String(), nullable=False, server_default='chat'))
    op.add_column('leads', sa.Column('email', sa.String(), nullable=True))
    op.add_column('leads', sa.Column('budget', sa.String(), nullable=True))
    op.add_column('leads', sa.Column('timeline', sa.String(), nullable=True))
    op.add_column('leads', sa.Column('intent', sa.String(), nullable=True))
    # web leads have no Telegram id
    op.alter_column('leads', 'telegram_id', existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    op.alter_column('leads', 'telegram_id', existing_type=sa.Integer(), nullable=False)
    op.drop_column('leads', 'intent')
    op.drop_column('leads', 'timeline')
    op.drop_column('leads', 'budget')
    op.drop_column('leads', 'email')
    op.drop_column('leads', 'source')
