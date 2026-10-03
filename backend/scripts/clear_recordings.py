"""Delete recordings and their associated assets.

Removes the database row, the stored audio (and read-aloud summary audio), and the
vector index for each matching recording. User accounts are left untouched.

Usage (from backend/):
    python -m scripts.clear_recordings                 # delete all recordings
    python -m scripts.clear_recordings --status failed # only failed recordings
"""
from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import AudioNote, ProcessingStatus
from app.rag import delete_note_from_rag
from app.supabase_storage import delete_audio_from_supabase, is_supabase_ref


def _remove_stored(path: str | None, note_id: str) -> None:
    if not path:
        return
    if is_supabase_ref(path) or path.startswith(("http://", "https://")):
        try:
            delete_audio_from_supabase(path)
        except Exception as exc:  # noqa: BLE001
            print(f"  storage delete failed for {note_id}: {exc}")
    else:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError as exc:
            print(f"  file delete failed for {note_id}: {exc}")


def clear(status: ProcessingStatus | None = None) -> int:
    deleted = 0
    with SessionLocal() as db:
        stmt = select(AudioNote)
        if status is not None:
            stmt = stmt.where(AudioNote.status == status)
        notes = db.scalars(stmt).all()
        for note in notes:
            print(f"- {note.id[:8]} [{note.status.value}] {note.filename}")
            _remove_stored(note.file_path, note.id)
            _remove_stored(note.summary_audio_path, note.id)
            try:
                delete_note_from_rag(note.id)
            except Exception as exc:  # noqa: BLE001
                print(f"  vector delete failed for {note.id}: {exc}")
            db.delete(note)
            deleted += 1
        db.commit()
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="Delete recordings and their assets.")
    parser.add_argument("--status", choices=[s.value for s in ProcessingStatus], default=None)
    args = parser.parse_args()
    status = ProcessingStatus(args.status) if args.status else None
    count = clear(status)
    print(f"Deleted {count} recording(s).")


if __name__ == "__main__":
    main()
