"""add tracking_number to orders

Revision ID: a1b2c3d4e5f6
Revises: d8177ef90091
Create Date: 2026-03-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "d8177ef90091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("tracking_number", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "tracking_number")
