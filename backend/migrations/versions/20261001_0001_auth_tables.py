"""Add authentication tables and reconcile existing audio notes columns.

Revision ID: 20261001_0001
Revises:
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261001_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "audio_notes" not in tables:
        op.create_table(
            "audio_notes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("file_path", sa.String(1024), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("language_code", sa.String(16), nullable=False, server_default="en-IN"),
            sa.Column("status", sa.String(11), nullable=False, server_default="queued"),
            sa.Column("transcript", sa.Text()),
            sa.Column("summary", sa.Text()),
            sa.Column("transcription_engine", sa.String(64)),
            sa.Column("summary_model", sa.String(64)),
            sa.Column("error_message", sa.Text()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    else:
        columns = {column["name"] for column in inspector.get_columns("audio_notes")}
        with op.batch_alter_table("audio_notes") as batch:
            for name in ("transcription_engine", "summary_model"):
                if name not in columns:
                    batch.add_column(sa.Column(name, sa.String(64), nullable=True))

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("password_hash", sa.String(512), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )
    else:
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "token_version" not in columns:
            op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))

    if "password_reset_tokens" not in tables:
        op.create_table(
            "password_reset_tokens",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

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
    op.drop_index("ix_email_verification_tokens_user_id", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_table("users")
