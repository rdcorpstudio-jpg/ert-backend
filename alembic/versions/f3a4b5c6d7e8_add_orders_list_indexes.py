"""indexes for order list queries (created_at, status, payments, alerts)

Revision ID: f3a4b5c6d7e8
Revises: e2a3b4c5d6e7
Create Date: 2026-03-27
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_orders_created_at", "orders", ["created_at"], unique=False)
    op.create_index("ix_orders_order_status", "orders", ["order_status"], unique=False)
    op.create_index("ix_orders_shipping_date", "orders", ["shipping_date"], unique=False)
    op.create_index("ix_order_payments_payment_status", "order_payments", ["payment_status"], unique=False)
    op.create_index("ix_order_payments_payment_method", "order_payments", ["payment_method"], unique=False)
    op.create_index(
        "ix_order_alerts_order_id_is_read",
        "order_alerts",
        ["order_id", "is_read"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_order_alerts_order_id_is_read", table_name="order_alerts")
    op.drop_index("ix_order_payments_payment_method", table_name="order_payments")
    op.drop_index("ix_order_payments_payment_status", table_name="order_payments")
    op.drop_index("ix_orders_shipping_date", table_name="orders")
    op.drop_index("ix_orders_order_status", table_name="orders")
    op.drop_index("ix_orders_created_at", table_name="orders")
