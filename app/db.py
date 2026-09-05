"""SQLite-backed analysis cache.

Tracks are keyed by their stable id. A ``fingerprint`` (file size + mtime, or the
Drive modifiedTime) lets us detect when a file changed and needs re-analysis, so
a folder of ~200 tracks is only analysed once.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import unicodedata
from collections import defaultdict
from typing import Optional

from .config import DB_PATH
from .models import SavedMix, Track

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
    fingerprint   TEXT,
    user_edited   TEXT
);

CREATE TABLE IF NOT EXISTS mixes (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    track_ids   TEXT,
    created_at  TEXT,
    updated_at  TEXT
);

-- Single-row control record + queue for the analysis job, so a part-finished
-- run can resume after the app restarts.
CREATE TABLE IF NOT EXISTS analysis_meta (
    id         INTEGER PRIMARY KEY CHECK (id = 1),
    running    INTEGER DEFAULT 0,
    paused     INTEGER DEFAULT 0,
    total      INTEGER DEFAULT 0,
    done       INTEGER DEFAULT 0,
    current    TEXT,
    folder_id  TEXT,
    started_at REAL
);

CREATE TABLE IF NOT EXISTS analysis_queue (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id    TEXT,
    name        TEXT,
    local_path  TEXT,
    fingerprint TEXT,
    status      TEXT
);

-- The single shared "current mix" sequence (desktop <-> mobile companion).
CREATE TABLE IF NOT EXISTS current_mix (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    track_ids TEXT
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.executescript(_SCHEMA)
        # Migrate older databases that predate the user_edited column.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(tracks)").fetchall()}
        if "user_edited" not in cols:
            conn.execute("ALTER TABLE tracks ADD COLUMN user_edited TEXT")


def _row_to_track(row: sqlite3.Row) -> Track:
    data = dict(row)
    data.pop("fingerprint", None)
    data["analyzed"] = bool(data.get("analyzed"))
    peaks = data.get("peaks")
    data["peaks"] = json.loads(peaks) if peaks else None
    ue = data.get("user_edited")
    data["user_edited"] = json.loads(ue) if ue else []
    return Track(**data)


def upsert_track(track: Track, fingerprint: Optional[str] = None) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            """
            INSERT INTO tracks (id, drive_id, name, artist, filename, local_path,
                duration, genre, bpm, key_camelot, key_name, energy, loudness,
                key_confidence, bpm_confidence, analyzed, peaks, error, fingerprint,
                user_edited)
            VALUES (:id, :drive_id, :name, :artist, :filename, :local_path,
                :duration, :genre, :bpm, :key_camelot, :key_name, :energy, :loudness,
                :key_confidence, :bpm_confidence, :analyzed, :peaks, :error, :fingerprint,
                :user_edited)
            ON CONFLICT(id) DO UPDATE SET
                drive_id=excluded.drive_id, name=excluded.name, artist=excluded.artist,
                filename=excluded.filename, local_path=excluded.local_path,
                duration=excluded.duration, genre=excluded.genre, bpm=excluded.bpm,
                key_camelot=excluded.key_camelot, key_name=excluded.key_name,
                energy=excluded.energy, loudness=excluded.loudness,
                key_confidence=excluded.key_confidence, bpm_confidence=excluded.bpm_confidence,
                analyzed=excluded.analyzed, peaks=excluded.peaks, error=excluded.error,
                fingerprint=excluded.fingerprint, user_edited=excluded.user_edited
            """,
            {
                **track.model_dump(),
                "peaks": json.dumps(track.peaks) if track.peaks else None,
                "analyzed": 1 if track.analyzed else 0,
                "fingerprint": fingerprint,
                "user_edited": json.dumps(track.user_edited or []),
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


# --------------------------------------------------------------------------- #
# Saved mixes
# --------------------------------------------------------------------------- #
def _row_to_mix(row: sqlite3.Row) -> SavedMix:
    data = dict(row)
    ids = data.get("track_ids")
    data["track_ids"] = json.loads(ids) if ids else []
    return SavedMix(**data)


def save_mix(mix: SavedMix) -> SavedMix:
    with _lock, _connect() as conn:
        conn.execute(
            """
            INSERT INTO mixes (id, name, description, track_ids, created_at, updated_at)
            VALUES (:id, :name, :description, :track_ids, :created_at, :updated_at)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, description=excluded.description,
                track_ids=excluded.track_ids, updated_at=excluded.updated_at
            """,
            {
                "id": mix.id,
                "name": mix.name,
                "description": mix.description,
                "track_ids": json.dumps(mix.track_ids),
                "created_at": mix.created_at,
                "updated_at": mix.updated_at,
            },
        )
    return mix


def list_mixes() -> list[SavedMix]:
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT * FROM mixes ORDER BY updated_at DESC").fetchall()
    return [_row_to_mix(r) for r in rows]


def get_mix(mix_id: str) -> Optional[SavedMix]:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM mixes WHERE id=?", (mix_id,)).fetchone()
    return _row_to_mix(row) if row else None


def delete_mix(mix_id: str) -> None:
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM mixes WHERE id=?", (mix_id,))


# --------------------------------------------------------------------------- #
# Library querying: paging / sorting / filtering + health
# --------------------------------------------------------------------------- #
def _load_all() -> list[Track]:
    with _lock, _connect() as conn:
        rows = conn.execute("SELECT * FROM tracks").fetchall()
    return [_row_to_track(r) for r in rows]


def _norm(s: Optional[str]) -> str:
    """Normalise a title/artist for duplicate detection (case/punctuation-insensitive)."""
    s = unicodedata.normalize("NFKD", (s or "").lower())
    return re.sub(r"[^a-z0-9]+", "", s)


def _camelot_sort_key(code: Optional[str]) -> tuple[int, str]:
    """Order by Camelot NUMBER then letter (1A,1B,2A,…); unknown keys sort last."""
    if not code or len(code) < 2:
        return (99, "Z")
    letter = code[-1].upper()
    try:
        num = int(code[:-1])
    except ValueError:
        return (99, "Z")
    if letter not in ("A", "B") or not 1 <= num <= 12:
        return (99, "Z")
    return (num, letter)


def _dupe_ids(tracks: list[Track], within: Optional[float] = None) -> set[str]:
    """Ids of tracks sharing a normalised name+artist with another track.

    When ``within`` is given, only count as duplicates if another same-named
    track is within that many seconds (or a duration is missing on either side).
    """
    groups: dict[tuple[str, str], list[Track]] = defaultdict(list)
    for t in tracks:
        groups[(_norm(t.name), _norm(t.artist))].append(t)
    out: set[str] = set()
    for items in groups.values():
        if len(items) < 2:
            continue
        if within is None:
            out.update(t.id for t in items)
            continue
        for t in items:
            for u in items:
                if u.id == t.id:
                    continue
                if t.duration is None or u.duration is None or abs(t.duration - u.duration) <= within:
                    out.add(t.id)
                    break
    return out


def query_tracks(
    offset: int = 0,
    limit: Optional[int] = None,
    sort: str = "title",
    direction: str = "asc",
    q: Optional[str] = None,
    crate: str = "all",
    bpm_min: Optional[float] = None,
    bpm_max: Optional[float] = None,
) -> tuple[list[Track], int]:
    """Return (page_of_tracks, total_matching). ``limit=None`` returns all."""
    all_tracks = _load_all()

    ql = (q or "").strip().lower()

    def matches_q(t: Track) -> bool:
        if not ql:
            return True
        hay = " ".join([t.name or "", t.artist or "", t.genre or "", t.key_camelot or ""]).lower()
        return ql in hay

    filtered = [t for t in all_tracks if matches_q(t)]
    if bpm_min is not None:
        filtered = [t for t in filtered if t.bpm is not None and t.bpm >= bpm_min]
    if bpm_max is not None:
        filtered = [t for t in filtered if t.bpm is not None and t.bpm <= bpm_max]

    if crate == "unanalysed":
        filtered = [t for t in filtered if not t.analyzed]
    elif crate == "nogenre":
        filtered = [t for t in filtered if not (t.genre and t.genre.strip())]
    elif crate == "lowconf":
        filtered = [t for t in filtered if t.analyzed and t.key_confidence is not None and t.key_confidence < 0.6]
    elif crate == "dupes":
        dset = _dupe_ids(all_tracks, None)
        filtered = [t for t in filtered if t.id in dset]

    keymap = {
        "title": lambda t: (t.name or "").lower(),
        "artist": lambda t: (t.artist or "").lower(),
        "genre": lambda t: (t.genre or "").lower(),
        "bpm": lambda t: (t.bpm if t.bpm is not None else -1.0),
        "energy": lambda t: (t.energy if t.energy is not None else -1.0),
        "duration": lambda t: (t.duration if t.duration is not None else -1.0),
        "key": lambda t: _camelot_sort_key(t.key_camelot),
    }
    keyfn = keymap.get(sort, keymap["title"])
    filtered.sort(key=keyfn, reverse=(direction == "desc"))

    total = len(filtered)
    page = filtered[offset:] if limit is None else filtered[offset:offset + limit]
    return page, total


def library_health() -> dict:
    tracks = _load_all()
    return {
        "total": len(tracks),
        "unanalysed": sum(1 for t in tracks if not t.analyzed),
        "missing_genre": sum(1 for t in tracks if not (t.genre and t.genre.strip())),
        "low_confidence_key": sum(
            1 for t in tracks if t.analyzed and t.key_confidence is not None and t.key_confidence < 0.6
        ),
        "duplicates": len(_dupe_ids(tracks, within=5.0)),
    }


# --------------------------------------------------------------------------- #
# Current shared mix (desktop <-> mobile companion)
# --------------------------------------------------------------------------- #
def get_current_mix() -> list[str]:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT track_ids FROM current_mix WHERE id=1").fetchone()
    if row and row["track_ids"]:
        try:
            return json.loads(row["track_ids"])
        except json.JSONDecodeError:
            return []
    return []


def set_current_mix(track_ids: list[str]) -> None:
    with _lock, _connect() as conn:
        conn.execute(
            "INSERT INTO current_mix (id, track_ids) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET track_ids=excluded.track_ids",
            (json.dumps(track_ids),),
        )


# --------------------------------------------------------------------------- #
# Analysis job persistence (resumable across restarts)
# --------------------------------------------------------------------------- #
def analysis_reset() -> None:
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM analysis_queue")
        conn.execute("DELETE FROM analysis_meta WHERE id=1")


def analysis_set_queue(items: list[dict]) -> None:
    """Replace the queue with ``items`` (each: track_id, name, local_path, fingerprint)."""
    with _lock, _connect() as conn:
        conn.execute("DELETE FROM analysis_queue")
        conn.executemany(
            "INSERT INTO analysis_queue (track_id, name, local_path, fingerprint, status) "
            "VALUES (:track_id, :name, :local_path, :fingerprint, NULL)",
            [
                {
                    "track_id": it.get("track_id"),
                    "name": it.get("name"),
                    "local_path": it.get("local_path"),
                    "fingerprint": it.get("fingerprint"),
                }
                for it in items
            ],
        )


def analysis_meta_set(**fields) -> None:
    allowed = {"running", "paused", "total", "done", "current", "folder_id", "started_at"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    with _lock, _connect() as conn:
        conn.execute("INSERT OR IGNORE INTO analysis_meta (id) VALUES (1)")
        sets = ", ".join(f"{k}=:{k}" for k in fields)
        conn.execute(f"UPDATE analysis_meta SET {sets} WHERE id=1", fields)


def analysis_meta_get() -> dict:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT * FROM analysis_meta WHERE id=1").fetchone()
    if not row:
        return {"running": 0, "paused": 0, "total": 0, "done": 0, "current": "", "folder_id": "", "started_at": None}
    d = dict(row)
    d["running"] = bool(d.get("running"))
    d["paused"] = bool(d.get("paused"))
    return d


def analysis_next_pending() -> Optional[dict]:
    with _lock, _connect() as conn:
        row = conn.execute(
            "SELECT * FROM analysis_queue WHERE status IS NULL ORDER BY seq ASC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def analysis_pending_count() -> int:
    with _lock, _connect() as conn:
        row = conn.execute("SELECT COUNT(*) c FROM analysis_queue WHERE status IS NULL").fetchone()
    return int(row["c"]) if row else 0


def analysis_mark(seq: int, status: str) -> None:
    with _lock, _connect() as conn:
        conn.execute("UPDATE analysis_queue SET status=? WHERE seq=?", (status, seq))


def analysis_counts() -> tuple[int, int]:
    """Return (done, total) from the queue."""
    with _lock, _connect() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM analysis_queue").fetchone()["c"]
        done = conn.execute("SELECT COUNT(*) c FROM analysis_queue WHERE status IS NOT NULL").fetchone()["c"]
    return int(done), int(total)


def analysis_recent(limit: int = 10) -> list[dict]:
    """Last ``limit`` finished files, newest first: id, name, key_camelot, bpm, status."""
    with _lock, _connect() as conn:
        rows = conn.execute(
            """
            SELECT q.track_id AS id,
                   COALESCE(t.name, q.name) AS name,
                   t.key_camelot AS key_camelot,
                   t.bpm AS bpm,
                   q.status AS status
            FROM analysis_queue q
            LEFT JOIN tracks t ON t.id = q.track_id
            WHERE q.status IS NOT NULL
            ORDER BY q.seq DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
