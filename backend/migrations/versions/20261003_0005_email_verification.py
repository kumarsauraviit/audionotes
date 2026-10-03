"""Restore email verification without changing access-token authentication.

Revision ID: 20261003_0005
Revises: 20261003_0004
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261003_0005"
down_revision = "20261003_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "users" in tables:
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "is_verified" not in columns:
            op.add_column(
                "users",
                sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
            )
    if "email_verification_tokens" not in tables:
        op.create_table(
            "email_verification_tokens",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_email_verification_tokens_user_id", "email_verification_tokens", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "email_verification_tokens" in tables:
        indexes = {index["name"] for index in inspect(bind).get_indexes("email_verification_tokens")}
        if "ix_email_verification_tokens_user_id" in indexes:
            op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
        op.drop_table("email_verification_tokens")
    if "users" in tables:
        columns = {column["name"] for column in inspect(bind).get_columns("users")}
        if "is_verified" in columns:
            op.drop_column("users", "is_verified")
