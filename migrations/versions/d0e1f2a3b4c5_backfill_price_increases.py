"""backfill previous_price for price increases cleared by c9d0e1f2a3b4

The prior cleanup nulled previous_price on rows where the price had risen
(false drops). Restore previous_price from price_history so the "price went
up" UI shows immediately, without waiting for the next price change.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-06-24 14:30:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # For each listing missing previous_price, take the most recent historical
    # price that differs from the current price; set it only when it is lower
    # than the current price (i.e. the price has risen since).
    op.execute(
        """
        UPDATE properties p
        SET previous_price = sub.prev
        FROM (
            SELECT DISTINCT ON (ph.property_id) ph.property_id, ph.price AS prev
            FROM price_history ph
            JOIN properties pr ON pr.id = ph.property_id
            WHERE ph.price <> pr.price
            ORDER BY ph.property_id, ph.observed_at DESC
        ) sub
        WHERE p.id = sub.property_id
          AND p.previous_price IS NULL
          AND p.price IS NOT NULL
          AND sub.prev < p.price
        """
    )


def downgrade() -> None:
    pass
