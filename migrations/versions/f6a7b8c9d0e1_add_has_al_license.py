"""add has_al_license column to properties

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-23 04:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('properties', sa.Column('has_al_license', sa.Boolean(), nullable=True))
    op.create_index('ix_properties_has_al_license', 'properties', ['has_al_license'])


def downgrade() -> None:
    op.drop_index('ix_properties_has_al_license', table_name='properties')
    op.drop_column('properties', 'has_al_license')
