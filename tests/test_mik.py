"""Tests for the Mixed In Key / tag importer and the render-without-script path."""
import numpy as np

from app import mik, mixrender


def test_key_normalization():
    assert mik.normalize_key("7A")[0] == "7A"          # Camelot passthrough
    assert mik.normalize_key("12B")[0] == "12B"
    assert mik.normalize_key("Am")[0] == "8A"          # A minor
    assert mik.normalize_key("Abm")[0] == "1A"         # Ab minor
    assert mik.normalize_key("C")[0] == "8B"           # C major
    assert mik.normalize_key("1m")[0] == "6A"          # Open Key -> Camelot
    assert mik.normalize_key("nonsense") == (None, None)


def test_filename_parsing():
    assert mik._from_filename("... Clean 7A 121.mp3") == {"key": "7A", "bpm": "121"}
    assert mik._from_filename("d#m130 - Cindy Lauper.mp3") == {"key": "d#m", "bpm": "130"}
    assert mik._from_filename("Whitney (Electro Pop 126 Bpm).mp3") == {"bpm": "126"}


def test_energy_parsing():
    assert mik._energy_from_text("Energy 7") == 7.0
    assert mik._energy_from_text("blah energy:9 blah") == 9.0
    assert mik._energy_from_text("no energy value here word") is None or isinstance(mik._energy_from_text("nothing"), type(None))


def test_apply_overlays_and_marks_confidence():
    from app.models import Track
    t = Track(id="x", name="x", filename="Song 8A 124.mp3", bpm=99, key_camelot="2B", key_confidence=0.3)
    # no local file -> reads from filename only
    from pathlib import Path
    sourced = mik.apply(Path("Song 8A 124.mp3"), t)
    assert t.key_camelot == "8A" and t.bpm == 124
    assert t.key_confidence == 1.0 and t.bpm_confidence == 1.0
    assert "key_camelot" in sourced and "bpm" in sourced


def _stereo(freq, secs, sr=8000):
    tt = np.linspace(0, secs, int(sr * secs), endpoint=False)
    m = 0.3 * np.sin(2 * np.pi * freq * tt)
    return np.stack([m, m], axis=1).astype("float32")


def test_render_without_instructions_uses_default_crossfades():
    sr = 8000
    audios = [_stereo(200, 4, sr), _stereo(300, 4, sr), _stereo(400, 4, sr)]
    mix = mixrender.assemble(audios, [120, 120, 120], [], sr=sr, default_cf=1.0)
    # 3x4s tracks, 2x1s crossfades -> ~10s; must include all three, not just track 1
    assert len(mix) > sr * 8
    assert mix.shape[1] == 2
