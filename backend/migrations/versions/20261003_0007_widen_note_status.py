"""Widen audio_notes.status so newer ProcessingStatus values fit.

Revision ID: 20261003_0007
Revises: 20261003_0006
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261003_0007"
down_revision = "20261003_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "audio_notes" not in inspect(bind).get_table_names():
        return
    # The initial migration created status as VARCHAR(11), but ProcessingStatus
    # now includes "transcribing" (12 chars) and "complete_with_warnings" (22).
    # SQLite ignores VARCHAR length, so this only surfaced on PostgreSQL.
    with op.batch_alter_table("audio_notes") as batch:
        batch.alter_column("status", type_=sa.String(32), existing_nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    if "audio_notes" not in inspect(bind).get_table_names():
        return
    with op.batch_alter_table("audio_notes") as batch:
        batch.alter_column("status", type_=sa.String(11), existing_nullable=False)
