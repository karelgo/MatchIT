"""initial schema: users, profiles, assignments, matches, refresh tokens

Revision ID: 0001
Revises:
Create Date: 2026-07-25

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("apple_user_id", sa.String(255), nullable=True, unique=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "freelancer",
                "employee",
                "consultancy",
                "recruiter",
                "hiring_manager",
                "admin",
                name="userrole",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"], unique=True)

    op.create_table(
        "specialist_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("headline", sa.String(200), nullable=False),
        sa.Column("bio", sa.Text(), nullable=False),
        sa.Column("skills", JSONB(), nullable=False),
        sa.Column("languages", JSONB(), nullable=False),
        sa.Column("certifications", JSONB(), nullable=False),
        sa.Column("years_experience", sa.Integer(), nullable=False),
        sa.Column("hourly_rate", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("hours_per_week", sa.Integer(), nullable=False),
        sa.Column("available_from", sa.Date(), nullable=True),
        sa.Column(
            "remote_preference",
            sa.Enum(
                "remote",
                "hybrid",
                "onsite",
                name="remotepreference",
                native_enum=False,
                length=10,
            ),
            nullable=False,
        ),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("travel_distance_km", sa.Integer(), nullable=False),
        sa.Column("github_url", sa.String(500), nullable=True),
        sa.Column("linkedin_url", sa.String(500), nullable=True),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("trust_score", sa.Float(), nullable=False),
        sa.Column("trust_breakdown", JSONB(), nullable=False),
        *_timestamps(),
    )

    op.create_table(
        "company_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("industry", sa.String(100), nullable=False),
        sa.Column("size", sa.String(50), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        *_timestamps(),
    )

    op.create_table(
        "assignments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "company_id",
            sa.Uuid(),
            sa.ForeignKey("company_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_description", sa.Text(), nullable=False),
        sa.Column("requirements", JSONB(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "open",
                "matched",
                "in_progress",
                "completed",
                "cancelled",
                name="assignmentstatus",
                native_enum=False,
                length=15,
            ),
            nullable=False,
        ),
        *_timestamps(),
    )

    decision = sa.Enum(
        "pending", "accepted", "rejected", name="decision", native_enum=False, length=10
    )
    op.create_table(
        "matches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "assignment_id",
            sa.Uuid(),
            sa.ForeignKey("assignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "specialist_id",
            sa.Uuid(),
            sa.ForeignKey("specialist_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("breakdown", JSONB(), nullable=False),
        sa.Column("company_decision", decision, nullable=False),
        sa.Column("specialist_decision", decision, nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "suggested", "mutual", "closed", name="matchstatus", native_enum=False, length=10
            ),
            nullable=False,
        ),
        sa.UniqueConstraint("assignment_id", "specialist_id"),
        *_timestamps(),
    )


def downgrade() -> None:
    op.drop_table("matches")
    op.drop_table("assignments")
    op.drop_table("company_profiles")
    op.drop_table("specialist_profiles")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
