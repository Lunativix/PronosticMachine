"""tracked propositions

Revision ID: c8d4e1a09b33
Revises: b7e2a91c4d10
Create Date: 2026-09-25 15:10:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8d4e1a09b33"
down_revision: Union[str, Sequence[str], None] = "b7e2a91c4d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tracked_propositions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selection", sa.String(16), nullable=False),
        sa.Column("selection_label", sa.String(120), nullable=False),
        sa.Column("odds", sa.Float()),
        sa.Column("raw_probability", sa.Float(), nullable=False),
        sa.Column("calibrated_probability", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.Column("home_goals", sa.Integer()),
        sa.Column("away_goals", sa.Integer()),
    )


def downgrade() -> None:
    op.drop_table("tracked_propositions")
