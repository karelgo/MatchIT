"""contracts: engagement contracts per match

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-27

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contracts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "match_id",
            sa.Uuid(),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "pending_signatures",
                "active",
                "completed",
                "cancelled",
                name="contractstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("hourly_rate", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("hours_per_week", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("draft", JSONB(), nullable=False),
        sa.Column("company_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("specialist_signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("contracts")
