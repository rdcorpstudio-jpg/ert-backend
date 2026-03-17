"""add invoice_number to orders

Revision ID: e1a2b3c4d5f6
Revises: b2c3d4e5f6a7
Create Date: 2026-03-08
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e1a2b3c4d5f6"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("invoice_number", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "invoice_number")

