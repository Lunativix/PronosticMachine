"""paper experiment strategy

Revision ID: d9e5f2b10c44
Revises: c8d4e1a09b33
Create Date: 2026-09-25 18:30:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d9e5f2b10c44"
down_revision: Union[str, Sequence[str], None] = "c8d4e1a09b33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tracked_propositions", sa.Column("strategy", sa.String(24), nullable=False, server_default="agent"))
    op.add_column("tracked_propositions", sa.Column("paper_profit", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("tracked_propositions", "paper_profit")
    op.drop_column("tracked_propositions", "strategy")
