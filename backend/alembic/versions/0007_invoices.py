"""invoices: escrow-backed billing periods per contract

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-27

"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "contract_id",
            sa.Uuid(),
            sa.ForeignKey("contracts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "issued",
                "in_escrow",
                "released",
                "cancelled",
                name="invoicestatus",
                native_enum=False,
                length=15,
            ),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("vat_rate_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("vat_treatment", sa.String(20), nullable=False),
        sa.Column("vat_note", sa.String(300), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("commission_rate_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("commission_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("specialist_payout", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_reference", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("contract_id", "period_start"),
    )


def downgrade() -> None:
    op.drop_table("invoices")
