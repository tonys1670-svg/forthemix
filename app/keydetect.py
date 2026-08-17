"""Musical key detection and the Camelot wheel used for harmonic mixing.

Key is estimated with the Krumhansl-Schmuckler key-finding algorithm: correlate
the track's averaged chroma vector against the 24 major/minor key profiles and
take the best match. The result is mapped to Camelot notation (e.g. 8A) which is
what DJs use to judge whether two tracks are harmonically compatible.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

# Krumhansl-Kessler tonal hierarchy profiles.
_MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
_MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)

_PITCHES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Map (pitch-class, is_minor) -> Camelot code.
_CAMELOT: dict[tuple[str, bool], str] = {
    # Major keys (B ring)
    ("B", False): "1B", ("F#", False): "2B", ("C#", False): "3B", ("G#", False): "4B",
    ("D#", False): "5B", ("A#", False): "6B", ("F", False): "7B", ("C", False): "8B",
    ("G", False): "9B", ("D", False): "10B", ("A", False): "11B", ("E", False): "12B",
    # Minor keys (A ring)
    ("G#", True): "1A", ("D#", True): "2A", ("A#", True): "3A", ("F", True): "4A",
    ("C", True): "5A", ("G", True): "6A", ("D", True): "7A", ("A", True): "8A",
    ("E", True): "9A", ("B", True): "10A", ("F#", True): "11A", ("C#", True): "12A",
}


def detect_key(chroma_mean: np.ndarray) -> tuple[Optional[str], Optional[str], float]:
    """Return (camelot, key_name, confidence) from a 12-bin mean chroma vector."""
    if chroma_mean is None or len(chroma_mean) != 12:
        return None, None, 0.0

    vec = np.asarray(chroma_mean, dtype=float)
    if vec.sum() <= 0:
        return None, None, 0.0
    vec = vec - vec.mean()

    best_corr = -2.0
    second_corr = -2.0
    best_pitch = "C"
    best_minor = False

    for shift in range(12):
        rotated_major = np.roll(_MAJOR_PROFILE - _MAJOR_PROFILE.mean(), shift)
        rotated_minor = np.roll(_MINOR_PROFILE - _MINOR_PROFILE.mean(), shift)
        for profile, is_minor in ((rotated_major, False), (rotated_minor, True)):
            denom = np.linalg.norm(vec) * np.linalg.norm(profile)
            corr = float(np.dot(vec, profile) / denom) if denom else 0.0
            if corr > best_corr:
                second_corr = best_corr
                best_corr = corr
                best_pitch = _PITCHES[shift]
                best_minor = is_minor
            elif corr > second_corr:
                second_corr = corr

    key_name = f"{best_pitch} {'minor' if best_minor else 'major'}"
    camelot = _CAMELOT.get((best_pitch, best_minor))
    # Confidence = separation between the top two candidates, squashed to 0..1.
    confidence = max(0.0, min(1.0, (best_corr - second_corr) * 2.5 + 0.35))
    return camelot, key_name, round(confidence, 2)


def _parse_camelot(code: str) -> Optional[tuple[int, str]]:
    if not code or len(code) < 2:
        return None
    letter = code[-1].upper()
    try:
        number = int(code[:-1])
    except ValueError:
        return None
    if letter not in ("A", "B") or not 1 <= number <= 12:
        return None
    return number, letter


def harmonic_relation(from_code: Optional[str], to_code: Optional[str]) -> tuple[int, str]:
    """Score the harmonic compatibility of two Camelot codes.

    Returns (score 0..100, human description). Based on standard Camelot-wheel
    mixing rules: same key, adjacent hour, or relative major/minor are the safe
    'energy-neutral' moves; +7 (dominant) and the +/-2 jumps are usable lifts.
    """
    a = _parse_camelot(from_code) if from_code else None
    b = _parse_camelot(to_code) if to_code else None
    if not a or not b:
        return 50, "Key unknown — can't judge harmonic fit."

    (na, la), (nb, lb) = a, b
    diff = (nb - na) % 12

    if na == nb and la == lb:
        return 100, "Same key — perfectly harmonic."
    if na == nb and la != lb:
        return 92, "Relative major/minor — classic smooth switch."
    if la == lb and diff in (1, 11):
        return 90, "Adjacent on the wheel — energy-neutral, very smooth."
    if la == lb and diff == 7:
        return 78, "Dominant (+7) — an energetic but harmonic lift."
    if la == lb and diff == 5:
        return 76, "Subdominant (-5) — harmonic, slightly relaxing."
    if la == lb and diff == 2:
        return 62, "+2 semitone-family jump — a noticeable energy boost."
    if la == lb and diff == 10:
        return 58, "-2 move — usable but a touch darker."
    if diff == 0 and la != lb:
        return 70, "Same hour, opposite ring — a diagonal switch, usually fine."
    return 30, "Keys are distant — expect a harmonic clash unless mixed carefully."
