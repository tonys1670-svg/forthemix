"""Render a cue-pointed mix to a continuous audio file (+ short previews).

Design:
  * The mix runs at a constant reference tempo (the first track's BPM). Each
    track is time-stretched from its own BPM to the reference so beats lock —
    pitch is preserved (RubberBand if available, else a librosa phase-vocoder
    fallback). Cue points are given on the *original* track and mapped into the
    stretched timeline.
  * Transitions use an equal-power crossfade, or an EQ *bass-swap* (roll the
    outgoing low end out while the incoming bass takes over) when requested.

The pure array functions (``equal_power_crossfade``, ``bass_swap_crossfade``,
``assemble``) take audio + BPMs directly so they can be unit-tested without any
files or the RubberBand binary.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np


# --------------------------------------------------------------------------- #
# Time-stretch (beatmatch)
# --------------------------------------------------------------------------- #
def time_stretch(y: np.ndarray, rate: float, sr: int) -> np.ndarray:
    """Stretch stereo audio (n, ch) by ``rate`` (>1 = faster/shorter), pitch-preserving."""
    if abs(rate - 1.0) < 1e-3 or y.size == 0:
        return y
    y = np.atleast_2d(y.T).T if y.ndim == 1 else y
    try:
        import pyrubberband as pyrb
        out = np.stack([pyrb.time_stretch(y[:, c], sr, rate) for c in range(y.shape[1])], axis=1)
        return out.astype(np.float32)
    except Exception:
        import librosa
        chans = [librosa.effects.time_stretch(np.ascontiguousarray(y[:, c]), rate=rate)
                 for c in range(y.shape[1])]
        n = min(len(c) for c in chans)
        return np.stack([c[:n] for c in chans], axis=1).astype(np.float32)


# --------------------------------------------------------------------------- #
# Crossfades
# --------------------------------------------------------------------------- #
def equal_power_crossfade(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Equal-power blend of two equal-length stereo buffers (no volume dip)."""
    n = min(len(a), len(b))
    if n == 0:
        return a[:0]
    t = np.linspace(0.0, 1.0, n)[:, None]
    return (a[:n] * np.cos(t * np.pi / 2) + b[:n] * np.sin(t * np.pi / 2)).astype(np.float32)


def _crossover(x: np.ndarray, sr: int, cutoff: float = 200.0) -> tuple[np.ndarray, np.ndarray]:
    """Split into (low, high) bands at ``cutoff`` Hz."""
    try:
        from scipy.signal import butter, sosfilt
        sos_lo = butter(4, cutoff / (sr / 2), btype="low", output="sos")
        sos_hi = butter(4, cutoff / (sr / 2), btype="high", output="sos")
        low = sosfilt(sos_lo, x, axis=0)
        high = sosfilt(sos_hi, x, axis=0)
        return low.astype(np.float32), high.astype(np.float32)
    except Exception:
        return x, np.zeros_like(x)  # scipy missing -> behave like a plain crossfade


def bass_swap_crossfade(a: np.ndarray, b: np.ndarray, sr: int) -> np.ndarray:
    """Classic DJ bass-swap: highs crossfade smoothly; the low end is handed over
    around the midpoint so only one track's bass plays at a time."""
    n = min(len(a), len(b))
    if n == 0:
        return a[:0]
    a, b = a[:n], b[:n]
    a_lo, a_hi = _crossover(a, sr)
    b_lo, b_hi = _crossover(b, sr)
    t = np.linspace(0.0, 1.0, n)[:, None]

    hi = a_hi * np.cos(t * np.pi / 2) + b_hi * np.sin(t * np.pi / 2)
    lo_out = np.clip(1.0 - t / 0.5, 0.0, 1.0)   # outgoing bass gone by the midpoint
    lo_in = np.clip((t - 0.5) / 0.5, 0.0, 1.0)  # incoming bass in from the midpoint
    lo = a_lo * lo_out + b_lo * lo_in
    return (hi + lo).astype(np.float32)


# --------------------------------------------------------------------------- #
# Timeline assembly
# --------------------------------------------------------------------------- #
def _sec_to_played_index(sec: Optional[float], f: float, sr: int, fallback: int) -> int:
    if sec is None:
        return fallback
    return max(0, int((sec / f) * sr))


def assemble(
    audios: list[np.ndarray],
    bpms: list[Optional[float]],
    instructions: list,
    sr: int,
    default_cf: float = 8.0,
    beatmatch: bool = True,
) -> np.ndarray:
    """Build one continuous stereo mix.

    ``audios`` are per-track stereo arrays; ``instructions`` are MixInstruction-like
    objects (from_index/to_index 1-based, from_out_sec, to_in_sec, crossfade_sec,
    technique). Missing cue points fall back to end-of-track / start-of-track.
    """
    n = len(audios)
    if n == 0:
        return np.zeros((0, 2), dtype=np.float32)

    ref = next((b for b in bpms if b), None)
    factors = [
        (ref / b) if (beatmatch and ref and b) else 1.0
        for b in bpms
    ]
    played = [time_stretch(audios[i], factors[i], sr) for i in range(n)]

    # index instructions by outgoing track position
    instr_by_from = {}
    for ins in instructions:
        instr_by_from[ins.from_index] = ins

    result: list[np.ndarray] = []
    cur_pos = 0  # played-sample cursor into the current track
    for i in range(n):
        cur = played[i]
        if i == n - 1:
            result.append(cur[cur_pos:])  # last track plays to the end
            break

        # Use the script's instruction for this boundary if given, else a plain
        # default crossfade — so "Render mix" works even with no script typed.
        ins = instr_by_from.get(i + 1)
        cf = (ins.crossfade_sec if (ins and ins.crossfade_sec) else default_cf)
        cf_n = max(1, int(cf * sr))
        out_sec = ins.from_out_sec if ins else None
        in_sec = ins.to_in_sec if ins else None
        technique = ins.technique if ins else "crossfade"

        out_idx = _sec_to_played_index(out_sec, factors[i], sr, fallback=max(0, len(cur) - cf_n))
        result.append(cur[cur_pos:out_idx])

        nxt = played[i + 1]
        in_idx = _sec_to_played_index(in_sec, factors[i + 1], sr, fallback=0)
        a_tail = cur[out_idx:out_idx + cf_n]
        b_head = nxt[in_idx:in_idx + cf_n]
        m = min(len(a_tail), len(b_head))
        if m > 0:
            if technique == "eq_bass_swap":
                result.append(bass_swap_crossfade(a_tail[:m], b_head[:m], sr))
            else:
                result.append(equal_power_crossfade(a_tail[:m], b_head[:m]))
        cur_pos = in_idx + m  # continue the incoming track after the blend

    mix = np.concatenate(result, axis=0) if result else np.zeros((0, 2), dtype=np.float32)
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 1.0:
        mix = mix / peak
    return mix.astype(np.float32)


# --------------------------------------------------------------------------- #
# File-level helpers
# --------------------------------------------------------------------------- #
def load_stereo(path: str, sr: int) -> np.ndarray:
    """Load an audio file as float32 stereo (n, 2) at ``sr``.

    Tries soundfile first (fast, handles wav/flac/mp3 via libsndfile), then falls
    back to librosa/audioread which copes with more formats (m4a/aac/wma/…).
    """
    data = None
    file_sr = sr
    try:
        import soundfile as sf
        data, file_sr = sf.read(path, always_2d=True, dtype="float32")
    except Exception:
        data = None
    if data is None or data.size == 0:
        import librosa
        y, file_sr = librosa.load(path, sr=sr, mono=False)  # (channels, n) or (n,)
        y = np.atleast_2d(y)
        data = y.T if y.shape[0] <= 8 else y  # -> (n, channels)
        file_sr = sr  # librosa already resampled to sr

    if data.ndim == 1:
        data = data[:, None]
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    if file_sr != sr:
        import librosa
        data = np.stack([librosa.resample(np.ascontiguousarray(data[:, c]), orig_sr=file_sr, target_sr=sr)
                         for c in range(data.shape[1])], axis=1)
    return data.astype(np.float32)


def render_plan_to_file(tracks: list, instructions: list, dest: Path, sr: int = 44100,
                        default_cf: float = 8.0, beatmatch: bool = True) -> Path:
    """Render the whole plan (list of Track models, in order) to a WAV file."""
    import soundfile as sf

    audios = [load_stereo(t.local_path, sr) for t in tracks]
    bpms = [t.bpm for t in tracks]
    mix = assemble(audios, bpms, instructions, sr, default_cf, beatmatch)
    dest = Path(dest)
    if dest.suffix.lower() != ".wav":
        dest = dest.with_suffix(".wav")
    sf.write(str(dest), mix, sr)
    return dest


def render_segment_to_file(track_out, track_in, instr, dest: Path, sr: int = 44100,
                           default_cf: float = 8.0, beatmatch: bool = True,
                           context_sec: float = 8.0) -> Path:
    """Render just one transition (with a little context on each side) for audition."""
    import soundfile as sf

    a = load_stereo(track_out.local_path, sr)
    b = load_stereo(track_in.local_path, sr)
    # Reuse assemble on a two-track mini-plan; trim leading context.
    two = [a, b]
    bpms = [track_out.bpm, track_in.bpm]
    from .mixplan import MixInstruction
    cf = instr.crossfade_sec if instr.crossfade_sec else default_cf
    out_sec = instr.from_out_sec
    mini = MixInstruction(from_index=1, to_index=2, from_out_sec=out_sec,
                          to_in_sec=instr.to_in_sec, crossfade_sec=cf, technique=instr.technique)
    mix = assemble(two, bpms, [mini], sr, default_cf, beatmatch)

    # Keep only context around the blend so the preview is short.
    f_out = (bpms[0] and next((x for x in bpms if x), None) and (next((x for x in bpms if x)) / bpms[0])) or 1.0
    blend_played = int(((out_sec or 0) / f_out) * sr) if out_sec else max(0, len(a) - int(cf * sr))
    start = max(0, blend_played - int(context_sec * sr))
    end = min(len(mix), blend_played + int((cf + context_sec) * sr))
    seg = mix[start:end] if end > start else mix
    dest = Path(dest)
    if dest.suffix.lower() != ".wav":
        dest = dest.with_suffix(".wav")
    sf.write(str(dest), seg, sr)
    return dest
