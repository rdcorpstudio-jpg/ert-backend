"""add discount_rules table

Revision ID: i7j8k9l0m1n2
Revises: h6i7j8k9l0m1
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i7j8k9l0m1n2"
down_revision: Union[str, Sequence[str], None] = "h6i7j8k9l0m1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discount_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("discount_type", sa.String(length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        sa.table(
            "discount_rules",
            sa.column("value", sa.Numeric),
            sa.column("discount_type", sa.String),
            sa.column("is_active", sa.Boolean),
            sa.column("sort_order", sa.Integer),
        ),
        [
            {"value": 5, "discount_type": "percent", "is_active": True, "sort_order": 0},
            {"value": 8, "discount_type": "percent", "is_active": True, "sort_order": 1},
            {"value": 10, "discount_type": "percent", "is_active": True, "sort_order": 2},
            {"value": 15, "discount_type": "percent", "is_active": True, "sort_order": 3},
            {"value": 20, "discount_type": "percent", "is_active": True, "sort_order": 4},
            {"value": 1000, "discount_type": "baht", "is_active": True, "sort_order": 5},
            {"value": 1500, "discount_type": "baht", "is_active": True, "sort_order": 6},
        ],
    )


def downgrade() -> None:
    op.drop_table("discount_rules")
