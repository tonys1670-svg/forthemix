"""Tests for the additive library/analysis backend features."""
from fastapi.testclient import TestClient

import app.analysis as analysis
from app import jobs
from conftest import mk


# --------------------------------------------------------------------------- #
# Camelot key sort order (number then letter, not string compare)
# --------------------------------------------------------------------------- #
def test_camelot_key_sort(fresh_db):
    for i, k in enumerate(["10A", "2A", "1B", "2B", "1A", "9A"]):
        fresh_db.upsert_track(mk(f"t{i}", f"T{i}", key=k))

    page, total = fresh_db.query_tracks(sort="key", direction="asc")
    assert total == 6
    assert [t.key_camelot for t in page] == ["1A", "1B", "2A", "2B", "9A", "10A"]

    page_desc, _ = fresh_db.query_tracks(sort="key", direction="desc")
    assert [t.key_camelot for t in page_desc] == ["10A", "9A", "2B", "2A", "1B", "1A"]


def test_camelot_string_sort_would_be_wrong(fresh_db):
    # Guard: a naive string sort would put "10A" before "2A"; ours must not.
    for i, k in enumerate(["2A", "10A"]):
        fresh_db.upsert_track(mk(f"t{i}", f"T{i}", key=k))
    page, _ = fresh_db.query_tracks(sort="key", direction="asc")
    assert [t.key_camelot for t in page] == ["2A", "10A"]


# --------------------------------------------------------------------------- #
# Crate filters
# --------------------------------------------------------------------------- #
def test_crate_filters(fresh_db):
    fresh_db.upsert_track(mk("un", "Un", analyzed=False, genre="x", key="8A", keyconf=0.9))
    fresh_db.upsert_track(mk("ng", "NoGenre", analyzed=True, genre=None, key="8A", keyconf=0.9))
    fresh_db.upsert_track(mk("lc", "LowConf", analyzed=True, genre="house", key="8A", keyconf=0.4))
    fresh_db.upsert_track(mk("ok", "Okay", analyzed=True, genre="house", key="8A", keyconf=0.9))
    fresh_db.upsert_track(mk("d1", "Same Song", artist="A", analyzed=True, genre="house", key="8A", keyconf=0.9, dur=200))
    fresh_db.upsert_track(mk("d2", "same song!", artist="a", analyzed=True, genre="house", key="9A", keyconf=0.9, dur=201))

    def ids(crate):
        page, total = fresh_db.query_tracks(crate=crate)
        assert total == len(page)
        return {t.id for t in page}

    assert ids("unanalysed") == {"un"}
    assert ids("nogenre") == {"ng"}
    assert ids("lowconf") == {"lc"}
    assert ids("dupes") == {"d1", "d2"}   # normalised name+artist collide
    assert len(ids("all")) == 6


def test_query_filters_q_and_bpm(fresh_db):
    fresh_db.upsert_track(mk("a", "Warm Intro", genre="deep house", bpm=120, key="8A"))
    fresh_db.upsert_track(mk("b", "Cold Peak", genre="techno", bpm=132, key="9A"))
    fresh_db.upsert_track(mk("c", "Warm Roller", genre="house", bpm=128, key="10A"))

    page, total = fresh_db.query_tracks(q="warm")
    assert {t.id for t in page} == {"a", "c"} and total == 2

    page, total = fresh_db.query_tracks(bpm_min=126, bpm_max=134)
    assert {t.id for t in page} == {"b", "c"}

    # q also matches the Camelot key
    page, _ = fresh_db.query_tracks(q="9a")
    assert {t.id for t in page} == {"b"}


def test_paging_envelope_and_default_returns_all(fresh_db):
    for i in range(5):
        fresh_db.upsert_track(mk(f"t{i}", f"Track {i}", bpm=120 + i))
    page, total = fresh_db.query_tracks(offset=2, limit=2, sort="title")
    assert total == 5 and len(page) == 2
    # default: no limit -> everything
    page_all, total_all = fresh_db.query_tracks()
    assert total_all == 5 and len(page_all) == 5


# --------------------------------------------------------------------------- #
# Re-analysis must not overwrite user-edited fields
# --------------------------------------------------------------------------- #
def test_preserve_user_edits_helper(fresh_db):
    existing = mk("x", "Song", genre="deep house", key="8A", bpm=124, analyzed=True, keyconf=1.0)
    existing.user_edited = ["genre", "key_camelot"]
    fresh = mk("x", "Song", genre="techno", key="2B", bpm=128, analyzed=True, keyconf=0.5)

    jobs.preserve_user_edits(existing, fresh)

    assert fresh.genre == "deep house"      # protected
    assert fresh.key_camelot == "8A"        # protected
    assert fresh.key_confidence == 1.0      # pinned
    assert fresh.bpm == 128                 # bpm not edited -> updated
    assert set(fresh.user_edited) == {"genre", "key_camelot"}


def test_reanalysis_does_not_overwrite_user_edits(fresh_db, monkeypatch, tmp_path):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"not real audio")

    existing = mk("x", "Song", genre="deep house", key="8A", bpm=124, analyzed=True, keyconf=1.0)
    existing.user_edited = ["genre"]
    fresh_db.upsert_track(existing, "OLDfp")

    def fake_analyze(path, track, settings):
        track.genre = "techno"
        track.key_camelot = "2B"
        track.bpm = 130
        track.energy = 7
        track.analyzed = True
        return track

    monkeypatch.setattr(analysis, "analyze_track", fake_analyze)

    # NEWfp != OLDfp so this is a real re-analysis, not a cache hit.
    status = jobs.AnalysisJob()._process_one("x", "song.mp3", str(audio), "NEWfp", {})
    assert status == "analysed"

    t = fresh_db.get_track("x")
    assert t.genre == "deep house"      # user edit preserved
    assert t.key_camelot == "2B"        # not edited -> re-analysed value kept
    assert "genre" in t.user_edited


# --------------------------------------------------------------------------- #
# Endpoint smoke: edit records user_edited + confidence; envelopes present
# --------------------------------------------------------------------------- #
def test_patch_and_health_endpoints(fresh_db):
    from app.server import app

    fresh_db.upsert_track(mk("x", "Song", genre=None, key="8A", bpm=120, analyzed=True, keyconf=0.3))
    with TestClient(app) as c:
        r = c.patch("/api/tracks/x", json={"genre": "deep house", "bpm": 124})
        assert r.status_code == 200
        t = r.json()
        assert t["genre"] == "deep house"
        assert t["bpm_confidence"] == 1.0
        assert set(t["user_edited"]) >= {"genre", "bpm"}

        # bulk edit
        rb = c.patch("/api/tracks", json={"ids": ["x"], "genre": "techno"})
        assert rb.status_code == 200 and rb.json()["updated"][0]["genre"] == "techno"

        listing = c.get("/api/tracks?limit=1&sort=title").json()
        assert set(listing.keys()) >= {"tracks", "total", "offset", "limit"}

        health = c.get("/api/library/health").json()
        assert set(health.keys()) == {"total", "unanalysed", "missing_genre", "low_confidence_key", "duplicates"}

        # current mix round-trip
        c.put("/api/mix", json={"track_ids": ["x"]})
        assert c.get("/api/mix").json()["track_ids"] == ["x"]

        # audio devices endpoint responds (sounddevice may be absent)
        assert "devices" in c.get("/api/audio/devices").json()
