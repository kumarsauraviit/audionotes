"""Add processing telemetry, Gnani options, extraction, and user glossary.

Revision ID: 20261003_0003
Revises: 20261002_0002
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261003_0003"
down_revision = "20261002_0002"
branch_labels = None
depends_on = None


AUDIO_NOTE_COLUMNS = [
    ("detected_language", sa.String(16)),
    ("duration_seconds", sa.Float()),
    ("summary_status", sa.String(16)),
    ("extraction", sa.JSON()),
    ("chapters", sa.JSON()),
    ("speaker_labels", sa.JSON()),
    ("tags", sa.JSON()),
    ("stage", sa.String(32)),
    ("progress_percent", sa.Integer()),
    ("progress_message", sa.Text()),
    ("eta_seconds", sa.Integer()),
    ("gnani_status", sa.String(32)),
    ("gnani_job_id", sa.String(64)),
    ("gnani_request_id", sa.String(128)),
    ("with_diarization", sa.Boolean()),
    ("with_denoise", sa.Boolean()),
    ("bias_list", sa.JSON()),
    ("bias_score", sa.Float()),
    ("summary_audio_path", sa.String(1024)),
    ("summary_audio_voice", sa.String(64)),
    ("error_code", sa.String(64)),
    ("retry_count", sa.Integer()),
]

USER_COLUMNS = [
    ("glossary", sa.JSON()),
    ("default_language", sa.String(16)),
]

# Columns that must be NOT NULL with a server-side default for existing rows.
NOT_NULL_DEFAULTS = {
    "summary_status": "pending",
    "with_diarization": "false",
    "with_denoise": "false",
    "retry_count": "0",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "audio_notes" in tables:
        existing = {column["name"] for column in inspector.get_columns("audio_notes")}
        with op.batch_alter_table("audio_notes") as batch:
            for name, column_type in AUDIO_NOTE_COLUMNS:
                if name in existing:
                    continue
                server_default = NOT_NULL_DEFAULTS.get(name)
                batch.add_column(
                    sa.Column(
                        name,
                        column_type,
                        nullable=server_default is None,
                        server_default=server_default if isinstance(server_default, str) else None,
                    )
                )
            # Widen language_code to allow up to three comma-separated codes.
            if "language_code" in existing:
                batch.alter_column("language_code", type_=sa.String(32), existing_nullable=False)

    if "users" in tables:
        existing = {column["name"] for column in inspector.get_columns("users")}
        with op.batch_alter_table("users") as batch:
            for name, column_type in USER_COLUMNS:
                if name not in existing:
                    batch.add_column(sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "audio_notes" in tables:
        existing = {column["name"] for column in inspector.get_columns("audio_notes")}
        with op.batch_alter_table("audio_notes") as batch:
            for name, _ in AUDIO_NOTE_COLUMNS:
                if name in existing:
                    batch.drop_column(name)

    if "users" in tables:
        existing = {column["name"] for column in inspector.get_columns("users")}
        with op.batch_alter_table("users") as batch:
            for name, _ in USER_COLUMNS:
                if name in existing:
                    batch.drop_column(name)
