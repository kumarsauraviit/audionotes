"""Restore token_version required by access-token validation.

Revision ID: 20261003_0006
Revises: 20261003_0005
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261003_0006"
down_revision = "20261003_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "users" not in inspect(bind).get_table_names():
        return

    columns = {column["name"] for column in inspect(bind).get_columns("users")}
    if "token_version" not in columns:
        op.add_column(
            "users",
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "users" not in inspect(bind).get_table_names():
        return

    columns = {column["name"] for column in inspect(bind).get_columns("users")}
    if "token_version" in columns:
        op.drop_column("users", "token_version")
