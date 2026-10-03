"""Add timestamped transcript segments to audio notes.

Revision ID: 20261002_0002
Revises: 20261001_0001
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261002_0002"
down_revision = "20261001_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "audio_notes" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("audio_notes")}
    if "segments" not in columns:
        with op.batch_alter_table("audio_notes") as batch:
            batch.add_column(sa.Column("segments", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "audio_notes" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("audio_notes")}
    if "segments" in columns:
        with op.batch_alter_table("audio_notes") as batch:
            batch.drop_column("segments")
