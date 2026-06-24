"""clear false price drops (price increases mistakenly stored as drops)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-06-24 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Price increases were recorded with negative price_drop_percent/amount.
    # Clear those rows so the "price dropped" UI only reflects real drops.
    op.execute(
        "UPDATE properties SET previous_price = NULL, price_drop_amount = NULL, "
        "price_drop_percent = NULL WHERE price_drop_percent IS NOT NULL "
        "AND price_drop_percent <= 0"
    )


def downgrade() -> None:
    pass
