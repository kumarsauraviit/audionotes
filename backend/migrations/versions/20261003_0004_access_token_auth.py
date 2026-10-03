"""Remove email verification and refresh session state.

Revision ID: 20261003_0004
Revises: 20261003_0003
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261003_0004"
down_revision = "20261003_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "email_verification_tokens" in tables:
        indexes = {index["name"] for index in inspector.get_indexes("email_verification_tokens")}
        if "ix_email_verification_tokens_user_id" in indexes:
            op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
        op.drop_table("email_verification_tokens")
    if "users" in tables:
        columns = {column["name"] for column in inspector.get_columns("users")}
        drop = [name for name in ("is_verified", "token_version") if name in columns]
        if drop:
            with op.batch_alter_table("users") as batch:
                for name in drop:
                    batch.drop_column(name)


def downgrade() -> None:
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "users" in tables:
        columns = {column["name"] for column in inspect(bind).get_columns("users")}
        with op.batch_alter_table("users") as batch:
            if "is_verified" not in columns:
                batch.add_column(sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
            if "token_version" not in columns:
                batch.add_column(sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
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
