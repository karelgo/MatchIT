"""matches: record when each side decided

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-28

Transparency reports state who decided and when. `updated_at` cannot answer that
— it moves on any write — so each decision carries its own timestamp. Existing
rows keep NULL: we do not know when those decisions were taken, and inventing a
value would put a false claim into a signed document.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "matches", sa.Column("company_decided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "matches", sa.Column("specialist_decided_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("matches", "specialist_decided_at")
    op.drop_column("matches", "company_decided_at")
