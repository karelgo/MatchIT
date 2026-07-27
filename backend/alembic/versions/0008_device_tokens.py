"""device_tokens: push notification destinations

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-27

"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token", sa.String(200), nullable=False),
        sa.Column(
            "platform",
            sa.Enum("ios", name="deviceplatform", native_enum=False, length=10),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token"),
    )
    op.create_index("ix_device_tokens_token", "device_tokens", ["token"])


def downgrade() -> None:
    op.drop_index("ix_device_tokens_token", table_name="device_tokens")
    op.drop_table("device_tokens")
