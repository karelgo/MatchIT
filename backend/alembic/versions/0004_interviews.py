"""interviews: AI screening interviews per match

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-27

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interviews",
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
                "in_progress",
                "completed",
                name="interviewstatus",
                native_enum=False,
                length=15,
            ),
            nullable=False,
        ),
        sa.Column("plan", JSONB(), nullable=False),
        sa.Column("transcript", JSONB(), nullable=False),
        sa.Column("assessment", JSONB(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("interviews")
