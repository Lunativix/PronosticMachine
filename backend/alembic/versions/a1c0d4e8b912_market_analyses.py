"""market and combination analyses

Revision ID: a1c0d4e8b912
Revises: 666b59b38f67
Create Date: 2026-09-24 17:40:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c0d4e8b912"
down_revision: Union[str, Sequence[str], None] = "666b59b38f67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("match_id", sa.Integer(), sa.ForeignKey("matches.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version_id", sa.Integer(), sa.ForeignKey("model_versions.id")),
        sa.Column("model_version", sa.String(64), nullable=False),
        sa.Column("market", sa.String(32), nullable=False),
        sa.Column("selection", sa.String(32), nullable=False),
        sa.Column("odds", sa.Float()),
        sa.Column("model_probability", sa.Float()),
        sa.Column("market_probability", sa.Float()),
        sa.Column("edge", sa.Float()),
        sa.Column("expected_value", sa.Float()),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("confidence_level", sa.String(16), nullable=False),
        sa.Column("signal", sa.String(32), nullable=False),
        sa.Column("data_quality", sa.Float(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("calibration", sa.Float()),
        sa.Column("model_agreement", sa.Float()),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("sufficient_data", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_market_analyses_match_id", "market_analyses", ["match_id"])
    op.create_table(
        "combination_analyses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("combined_odds", sa.Float()),
        sa.Column("combined_probability", sa.Float()),
        sa.Column("combined_ev", sa.Float()),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("correlation_risk", sa.String(16), nullable=False),
        sa.Column("correlation_status", sa.String(32), nullable=False),
        sa.Column("combination_scope", sa.String(32), nullable=False),
        sa.Column("selections", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("combination_analyses")
    op.drop_index("ix_market_analyses_match_id", table_name="market_analyses")
    op.drop_table("market_analyses")
