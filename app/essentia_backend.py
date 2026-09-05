"""Optional Essentia analysis backend (pro-grade key/BPM + ML genre).

Essentia is heavier to install than librosa (see README), so it's entirely
optional: ``is_available()`` reports whether it imported, and the analysis
dispatcher only routes here when the user selects the "essentia" engine *and*
the import succeeds — otherwise ForTheMix falls back to librosa. Genre is
inferred with a Discogs EffNet model only when the user has configured a model
path; without one, genre still comes from the file's tags.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np

from .keydetect import camelot_from_key
from .models import Track

_SR = 44100


def is_available() -> bool:
    try:
        import essentia.standard  # noqa: F401
        return True
    except Exception:
        return False


def _compute_peaks(y: np.ndarray, buckets: int = 800) -> list[float]:
    if y.size == 0:
        return []
    step = max(1, y.size // buckets)
    reshaped = y[: (y.size // step) * step].reshape(-1, step)
    peaks = np.abs(reshaped).max(axis=1)
    peak_max = float(peaks.max()) or 1.0
    return [round(float(p) / peak_max, 3) for p in peaks]


def _predict_genre(audio: np.ndarray, model_path: str) -> Optional[str]:
    """Best-effort Discogs-EffNet genre prediction; returns None on any failure."""
    try:
        import essentia.standard as es

        embed_model = es.TensorflowPredictEffnetDiscogs(
            graphFilename=model_path, output="PartitionedCall:1"
        )
        embeddings = embed_model(audio)
        # A crude top-tag readout; production use would load class labels too.
        activations = np.mean(embeddings, axis=0)
        return f"genre#{int(np.argmax(activations))}"
    except Exception:
        return None


def analyze_file(path: Path, track: Track, energy_scale: int = 10,
                 genre_model: str = "") -> Track:
    """Populate ``track`` using Essentia. Assumes ``is_available()`` is True."""
    import essentia.standard as es

    # Read tags first (title/artist/genre) via the shared mutagen reader.
    from .analysis import read_tags

    tags = read_tags(path)
    if tags.get("title"):
        track.name = tags["title"] or track.name
    if tags.get("artist"):
        track.artist = tags["artist"]
    track.genre = tags.get("genre")

    try:
        audio = es.MonoLoader(filename=str(path), sampleRate=_SR)()
    except Exception as exc:
        track.error = f"Could not decode audio: {exc}"
        track.analyzed = False
        return track

    if audio.size == 0:
        track.error = "Empty or silent audio."
        track.analyzed = False
        return track

    track.duration = round(float(len(audio) / _SR), 1)

    # --- BPM ---------------------------------------------------------------
    try:
        rhythm = es.RhythmExtractor2013(method="multifeature")
        bpm, _beats, beats_conf, _, _ = rhythm(audio)
        track.bpm = round(float(bpm), 1)
        track.bpm_confidence = round(min(1.0, float(beats_conf) / 5.32), 2)
    except Exception:
        track.bpm = None
        track.bpm_confidence = 0.0

    # --- Key (Camelot) -----------------------------------------------------
    try:
        key, scale, strength = es.KeyExtractor()(audio)
        camelot, key_name = camelot_from_key(key, scale)
        track.key_camelot = camelot
        track.key_name = key_name
        track.key_confidence = round(float(strength), 2)
    except Exception:
        track.key_camelot = None
        track.key_name = None
        track.key_confidence = 0.0

    # --- Energy / loudness -------------------------------------------------
    try:
        rms = float(np.sqrt(np.mean(np.square(audio))))
        loudness = 20.0 * math.log10(max(rms, 1e-6))
        loud_norm = min(1.0, max(0.0, (loudness + 45.0) / 45.0))
        track.energy = round(loud_norm * energy_scale, 1)
        track.loudness = round(loudness, 1)
    except Exception:
        track.energy = None

    # --- Genre (optional ML model) ----------------------------------------
    if genre_model and Path(genre_model).exists():
        predicted = _predict_genre(audio, genre_model)
        if predicted:
            track.genre = predicted

    try:
        track.peaks = _compute_peaks(np.asarray(audio, dtype=float))
    except Exception:
        track.peaks = None

    track.error = None
    track.analyzed = True
    return track
