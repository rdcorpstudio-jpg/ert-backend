"""add deposit_amount to order_payments

Revision ID: g4h5i6j7k8l9
Revises: f3a4b5c6d7e8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "g4h5i6j7k8l9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "order_payments",
        sa.Column("deposit_amount", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_payments", "deposit_amount")
