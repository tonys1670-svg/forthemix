"""Per-track audio analysis: BPM, key (Camelot), energy, loudness, waveform peaks.

Genre is read from the file's embedded tags (librosa can't infer genre reliably),
and flagged as unknown when absent — matching the plan we agreed.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np

from . import config
from .keydetect import detect_key
from .models import Track

# Analyse at a reduced sample rate — plenty for BPM/key/energy and much faster.
_SR = 22050
# Number of waveform peaks to send to the UI player.
_PEAK_BUCKETS = 800


def read_tags(path: Path) -> dict[str, Optional[str]]:
    """Read title/artist/genre from embedded metadata, best-effort."""
    info: dict[str, Optional[str]] = {"title": None, "artist": None, "genre": None}
    try:
        from mutagen import File as MutagenFile

        mf = MutagenFile(path, easy=True)
        if mf and mf.tags:
            for src, dest in (("title", "title"), ("artist", "artist"), ("genre", "genre")):
                val = mf.tags.get(src)
                if val:
                    info[dest] = str(val[0]) if isinstance(val, list) else str(val)
    except Exception:
        pass
    return info


def _compute_peaks(y: np.ndarray, buckets: int = _PEAK_BUCKETS) -> list[float]:
    """Downsample the waveform to a normalized 0..1 peak envelope for drawing."""
    if y.size == 0:
        return []
    step = max(1, y.size // buckets)
    trimmed = y[: step * (y.size // step)] if y.size >= step else y
    if trimmed.size == 0:
        trimmed = y
    reshaped = trimmed[: (trimmed.size // step) * step].reshape(-1, step)
    peaks = np.abs(reshaped).max(axis=1)
    peak_max = float(peaks.max()) or 1.0
    return [round(float(p) / peak_max, 3) for p in peaks]


def _energy_score(y: np.ndarray, sr: int, scale: int) -> tuple[float, float]:
    """Return (energy 0..scale, loudness in dBFS-ish)."""
    import librosa

    rms = librosa.feature.rms(y=y)[0]
    mean_rms = float(np.mean(rms)) if rms.size else 1e-6
    loudness = 20.0 * math.log10(max(mean_rms, 1e-6))  # ~ -60..0

    # Blend loudness with spectral brightness so "energy" tracks perceived drive,
    # not just volume.
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    brightness = float(np.mean(centroid)) if centroid.size else 0.0
    bright_norm = min(1.0, brightness / (sr / 4.0))
    loud_norm = min(1.0, max(0.0, (loudness + 45.0) / 45.0))

    energy01 = 0.7 * loud_norm + 0.3 * bright_norm
    return round(energy01 * scale, 1), round(loudness, 1)


def analyze_file(path: Path, track: Track, energy_scale: int = 10) -> Track:
    """Populate ``track`` with analysis results from the audio at ``path``."""
    import librosa

    tags = read_tags(path)
    if tags.get("title"):
        track.name = tags["title"] or track.name
    if tags.get("artist"):
        track.artist = tags["artist"]
    track.genre = tags.get("genre")  # None -> flagged as unknown in UI

    try:
        y, sr = librosa.load(str(path), sr=_SR, mono=True)
    except Exception as exc:  # unreadable/corrupt/unsupported
        track.error = f"Could not decode audio: {exc}"
        track.analyzed = False
        return track

    if y.size == 0:
        track.error = "Empty or silent audio."
        track.analyzed = False
        return track

    track.duration = round(float(librosa.get_duration(y=y, sr=sr)), 1)

    # --- Tempo / BPM -------------------------------------------------------
    try:
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(np.atleast_1d(tempo)[0])
        # Fold obviously-doubled/halved tempos into a sane DJ range.
        while bpm > 180:
            bpm /= 2
        while bpm and bpm < 70:
            bpm *= 2
        track.bpm = round(bpm, 1)
        # Confidence from beat-strength consistency.
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        track.bpm_confidence = round(float(min(1.0, np.mean(onset_env) / (np.max(onset_env) + 1e-6) + 0.3)), 2)
    except Exception:
        track.bpm = None
        track.bpm_confidence = 0.0

    # --- Key (Camelot) -----------------------------------------------------
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = np.mean(chroma, axis=1)
        camelot, key_name, conf = detect_key(chroma_mean)
        track.key_camelot = camelot
        track.key_name = key_name
        track.key_confidence = conf
    except Exception:
        track.key_camelot = None
        track.key_name = None
        track.key_confidence = 0.0

    # --- Energy / loudness -------------------------------------------------
    try:
        energy, loudness = _energy_score(y, sr, energy_scale)
        track.energy = energy
        track.loudness = loudness
    except Exception:
        track.energy = None

    # --- Waveform peaks for the player ------------------------------------
    try:
        track.peaks = _compute_peaks(y)
    except Exception:
        track.peaks = None

    track.error = None
    track.analyzed = True
    return track


def analyze_track(path: Path, track: Track, settings: dict) -> Track:
    """Dispatch to the configured analysis engine, falling back to librosa.

    Essentia is used only when selected *and* importable; otherwise we quietly
    use librosa so analysis never hard-fails on a missing optional dependency.
    """
    energy_scale = int(settings.get("energy_scale", 10))
    engine = settings.get("analysis_engine", "librosa")

    used_essentia = False
    if engine == "essentia":
        try:
            from . import essentia_backend

            if essentia_backend.is_available():
                essentia_backend.analyze_file(
                    path, track, energy_scale,
                    genre_model=settings.get("essentia_genre_model", ""),
                )
                used_essentia = True
        except Exception:
            pass  # fall through to librosa

    if not used_essentia:
        analyze_file(path, track, energy_scale)

    # Overlay the user's Mixed In Key / ID3-tag values as the authoritative
    # source (they trust their own MIK analysis over our re-derivation).
    if settings.get("prefer_mik", True):
        try:
            from . import mik

            sourced = mik.apply(path, track)
            # If audio couldn't be decoded but tags gave us key/bpm, the track
            # is still usable — mark it analysed rather than an error.
            if not track.analyzed and ("key_camelot" in sourced or "bpm" in sourced):
                track.analyzed = True
                track.error = None
        except Exception:
            pass

    return track
