"""competition discovery fields

Revision ID: b7e2a91c4d10
Revises: a1c0d4e8b912
Create Date: 2026-09-24 17:40:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2a91c4d10"
down_revision: Union[str, Sequence[str], None] = "a1c0d4e8b912"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("competitions", sa.Column("provider", sa.String(40), nullable=False, server_default=""))
    op.add_column("competitions", sa.Column("provider_competition_id", sa.String(80)))
    op.add_column("competitions", sa.Column("normalized_name", sa.String(160)))
    op.add_column("competitions", sa.Column("country_code", sa.String(8)))
    op.add_column("competitions", sa.Column("continent", sa.String(40)))
    op.add_column("competitions", sa.Column("gender", sa.String(16)))
    op.add_column("competitions", sa.Column("age_category", sa.String(16)))
    op.add_column("competitions", sa.Column("competition_type", sa.String(32)))
    op.add_column("competitions", sa.Column("tier", sa.Integer()))
    op.add_column("competitions", sa.Column("current_season", sa.String(32)))
    op.add_column("competitions", sa.Column("season_start", sa.DateTime(timezone=True)))
    op.add_column("competitions", sa.Column("season_end", sa.DateTime(timezone=True)))
    op.add_column("competitions", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("competitions", sa.Column("fixtures_available", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("competitions", sa.Column("odds_available", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("competitions", sa.Column("last_sync", sa.DateTime(timezone=True)))
    op.add_column("competitions", sa.Column("source", sa.String(64)))


def downgrade() -> None:
    for name in (
        "source",
        "last_sync",
        "odds_available",
        "fixtures_available",
        "active",
        "season_end",
        "season_start",
        "current_season",
        "tier",
        "competition_type",
        "age_category",
        "gender",
        "continent",
        "country_code",
        "normalized_name",
        "provider_competition_id",
        "provider",
    ):
        op.drop_column("competitions", name)
