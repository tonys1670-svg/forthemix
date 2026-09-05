"""SQLite-backed analysis cache.

Tracks are keyed by their stable id. A ``fingerprint`` (file size + mtime, or the
Drive modifiedTime) lets us detect when a file changed and needs re-analysis, so
a folder of ~200 tracks is only analysed once.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Optional

from .config import DB_PATH
from .models import Track

_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id            TEXT PRIMARY KEY,
    drive_id      TEXT,
    name          TEXT,
    artist        TEXT,
    filename      TEXT,
    local_path    TEXT,
    duration      REAL,
    genre         TEXT,
    bpm           REAL,
    key_camelot   TEXT,
    key_name      TEXT,
    energy        REAL,
    loudness      REAL,
    key_confidence REAL,
    bpm_confidence REAL,
    analyzed      INTEGER DEFAULT 0,
    peaks         TEXT,
    error         TEXT,
    fingerprint   TEXT
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.executescript(_SCHEMA)


def _row_to_track(row: sqlite3.Row) -> Track:
    data = dict(row)
    data.pop("fingerprint", None)
    data["analyzed"] = bool(data.get("analyzed"))
    peaks = data.get("peaks")
    data["peaks"] = json.loads(peaks) if peaks else None
    return Track(**data)


def upsert_track(track: Track, fingerprint: Optional[str] = None) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            """
            INSERT INTO tracks (id, drive_id, name, artist, filename, local_path,
                duration, genre, bpm, key_camelot, key_name, energy, loudness,
                key_confidence, bpm_confidence, analyzed, peaks, error, fingerprint)
            VALUES (:id, :drive_id, :name, :artist, :filename, :local_path,
                :duration, :genre, :bpm, :key_camelot, :key_name, :energy, :loudness,
                :key_confidence, :bpm_confidence, :analyzed, :peaks, :error, :fingerprint)
            ON CONFLICT(id) DO UPDATE SET
                drive_id=excluded.drive_id, name=excluded.name, artist=excluded.artist,
                filename=excluded.filename, local_path=excluded.local_path,
                duration=excluded.duration, genre=excluded.genre, bpm=excluded.bpm,
                key_camelot=excluded.key_camelot, key_name=excluded.key_name,
                energy=excluded.energy, loudness=excluded.loudness,
                key_confidence=excluded.key_confidence, bpm_confidence=excluded.bpm_confidence,
                analyzed=excluded.analyzed, peaks=excluded.peaks, error=excluded.error,
                fingerprint=excluded.fingerprint
            """,
            {
                **track.model_dump(),
                "peaks": json.dumps(track.peaks) if track.peaks else None,
                "analyzed": 1 if track.analyzed else 0,
                "fingerprint": fingerprint,
            },
        )


def get_track(track_id: str) -> Optional[Track]:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
    return _row_to_track(row) if row else None


def get_fingerprint(track_id: str) -> Optional[str]:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT fingerprint FROM tracks WHERE id=?", (track_id,)).fetchone()
    return row["fingerprint"] if row else None


def list_tracks() -> list[Track]:
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT * FROM tracks ORDER BY name COLLATE NOCASE").fetchall()
    return [_row_to_track(r) for r in rows]


def delete_track(track_id: str) -> None:
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM tracks WHERE id=?", (track_id,))


def clear_all() -> None:
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM tracks")
