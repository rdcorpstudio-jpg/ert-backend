"""add is_active to freebies

Revision ID: h6i7j8k9l0m1
Revises: g4h5i6j7k8l9
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h6i7j8k9l0m1"
down_revision: Union[str, Sequence[str], None] = "g4h5i6j7k8l9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "freebies",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("freebies", "is_active")
