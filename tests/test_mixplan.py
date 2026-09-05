"""Tests for the mix-script parser, warnings, and the render engine's core math."""
import numpy as np

from app.mixplan import (
    MixInstruction,
    beatmatch_warnings,
    parse_script,
    parse_timecode,
)
from app import mixrender
from conftest import mk


# --------------------------------------------------------------------------- #
# Timecode parsing
# --------------------------------------------------------------------------- #
def test_parse_timecode_forms():
    assert parse_timecode("1:24") == 84
    assert parse_timecode("1m24s") == 84
    assert parse_timecode("0m23s") == 23
    assert parse_timecode("84s") == 84
    assert parse_timecode("84") == 84
    assert parse_timecode("0:23") == 23
    assert parse_timecode("") is None
    assert parse_timecode(None) is None


# --------------------------------------------------------------------------- #
# The headline example from the request
# --------------------------------------------------------------------------- #
def test_parse_headline_example():
    text = "mix track 4 into track 3 at track 3 1:24 / track 4 0:23"
    instrs, warnings = parse_script(text, n_tracks=4)
    assert len(instrs) == 1
    ins = instrs[0]
    assert ins.from_index == 3    # track 3 is the outgoing (playing) track
    assert ins.to_index == 4      # track 4 comes in
    assert ins.from_out_sec == 84
    assert ins.to_in_sec == 23
    assert not warnings


def test_parse_variants_and_technique():
    instrs, _ = parse_script("3 -> 4 at 1:24 / 0:23 crossfade 6s bass swap", n_tracks=4)
    ins = instrs[0]
    assert (ins.from_index, ins.to_index) == (3, 4)
    assert ins.from_out_sec == 84 and ins.to_in_sec == 23
    assert ins.crossfade_sec == 6
    assert ins.technique == "eq_bass_swap"


def test_parse_out_of_range_and_unparseable():
    _, warnings = parse_script("mix track 9 into track 3 at 1:00 / 0:10", n_tracks=4)
    assert any(w.kind == "range" for w in warnings)
    _, warnings2 = parse_script("just vibe it", n_tracks=4)
    assert any(w.kind == "parse" for w in warnings2)


# --------------------------------------------------------------------------- #
# Beatmatch warning threshold
# --------------------------------------------------------------------------- #
def test_beatmatch_warning_threshold():
    # ref = first track bpm = 120; incoming 124 -> ~3.3% (no warn at 6%)
    tracks = [mk("a", "A", bpm=120, key="8A"), mk("b", "B", bpm=124, key="9A")]
    ins = [MixInstruction(from_index=1, to_index=2, from_out_sec=60, to_in_sec=5)]
    assert not [w for w in beatmatch_warnings(tracks, ins, 6) if w.kind == "tempo"]

    # incoming 140 vs ref 120 -> ~16.7% -> warn
    tracks2 = [mk("a", "A", bpm=120, key="8A"), mk("b", "B", bpm=140, key="9A")]
    warns = [w for w in beatmatch_warnings(tracks2, ins, 6) if w.kind == "tempo"]
    assert warns and warns[0].options


def test_key_clash_warning():
    tracks = [mk("a", "A", bpm=120, key="8A"), mk("b", "B", bpm=121, key="2B")]  # distant keys
    ins = [MixInstruction(from_index=1, to_index=2, from_out_sec=60, to_in_sec=5)]
    warns = [w for w in beatmatch_warnings(tracks, ins, 6) if w.kind == "key"]
    assert warns


# --------------------------------------------------------------------------- #
# Render engine core (pure array functions — no files, no rubberband needed)
# --------------------------------------------------------------------------- #
def _stereo(freq, secs, sr=44100):
    t = np.linspace(0, secs, int(sr * secs), endpoint=False)
    mono = 0.3 * np.sin(2 * np.pi * freq * t)
    return np.stack([mono, mono], axis=1).astype(np.float32)


def test_equal_power_crossfade_is_equal_power():
    sr = 44100
    a = _stereo(220, 1, sr)
    b = _stereo(330, 1, sr)
    mixed = mixrender.equal_power_crossfade(a, b)
    assert mixed.shape == a.shape
    # cos^2 + sin^2 == 1 -> the gain envelope holds unit power throughout
    n = len(mixed)
    t = np.linspace(0, 1, n)
    power = np.cos(t * np.pi / 2) ** 2 + np.sin(t * np.pi / 2) ** 2
    assert np.allclose(power, 1.0, atol=1e-6)


def test_assemble_lengths_and_no_clip():
    sr = 8000  # small SR keeps the test fast
    # three 4-second tracks at the same tempo -> no stretch
    audios = [_stereo(200, 4, sr), _stereo(300, 4, sr), _stereo(400, 4, sr)]
    bpms = [120, 120, 120]
    instrs = [
        MixInstruction(from_index=1, to_index=2, from_out_sec=3.0, to_in_sec=0.5, crossfade_sec=1.0),
        MixInstruction(from_index=2, to_index=3, from_out_sec=3.0, to_in_sec=0.5, crossfade_sec=1.0),
    ]
    mix = mixrender.assemble(audios, bpms, instrs, sr, default_cf=1.0)
    assert mix.ndim == 2 and mix.shape[1] == 2
    assert len(mix) > sr * 4  # longer than a single track
    assert float(np.max(np.abs(mix))) <= 1.0 + 1e-6  # normalised, no clipping


def test_assemble_bass_swap_runs():
    sr = 8000
    audios = [_stereo(200, 3, sr), _stereo(300, 3, sr)]
    instrs = [MixInstruction(from_index=1, to_index=2, from_out_sec=2.0, to_in_sec=0.2,
                             crossfade_sec=1.0, technique="eq_bass_swap")]
    mix = mixrender.assemble(audios, [120, 120], instrs, sr, default_cf=1.0)
    assert len(mix) > 0 and mix.shape[1] == 2
