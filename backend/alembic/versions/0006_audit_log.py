"""audit_log: append-only security trail

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-27

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        # SET NULL, not CASCADE: erasing an account must not erase the record
        # that it existed and what it did.
        sa.Column(
            "actor_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "action",
            sa.Enum(
                "user_registered",
                "login_succeeded",
                "login_failed",
                "contract_signed",
                "data_exported",
                "account_deleted",
                name="auditaction",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("target_type", sa.String(50), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("client_ip", sa.String(45), nullable=True),
        sa.Column("context", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_log_action_created", "audit_log", ["action", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_action_created", table_name="audit_log")
    op.drop_table("audit_log")
