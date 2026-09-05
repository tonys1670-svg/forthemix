"""Shared pytest fixtures — isolate the SQLite DB to a temp file per test."""
import pytest

from app import db as _db
from app.models import Track


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(_db, "DB_PATH", str(tmp_path / "test.db"))
    _db.init_db()
    yield _db


def mk(id, name, artist=None, genre=None, bpm=None, key=None, energy=None,
       dur=None, analyzed=True, keyconf=None):
    return Track(
        id=id, name=name, filename=f"{id}.mp3", artist=artist, genre=genre,
        bpm=bpm, key_camelot=key, energy=energy, duration=dur,
        analyzed=analyzed, key_confidence=keyconf,
    )
