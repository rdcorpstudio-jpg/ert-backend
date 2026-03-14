"""add shipping_method to orders

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "4cafcce1b777"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("shipping_method", sa.String(20), nullable=False, server_default="Normal"),
    )
    # Ensure all existing rows have a value (in case server_default was not applied on some DBs, e.g. Railway)
    op.execute("UPDATE orders SET shipping_method = 'Normal' WHERE shipping_method IS NULL OR TRIM(COALESCE(shipping_method, '')) = ''")


def downgrade() -> None:
    op.drop_column("orders", "shipping_method")
