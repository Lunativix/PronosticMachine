"""information archive

Revision ID: e0f6a3c21d55
Revises: d9e5f2b10c44
Create Date: 2026-09-26 02:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0f6a3c21d55"
down_revision: Union[str, Sequence[str], None] = "d9e5f2b10c44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "information_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("external_key", sa.String(240), nullable=False, unique=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("url", sa.String(400)),
        sa.Column("body", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("information_items")
