"""Score and describe the transition from one track to the next.

Combines three DJ-relevant dimensions into a single 0..100 fit score plus a
human-readable comment for the comments window:

    * harmonic  — Camelot-wheel compatibility (see keydetect.harmonic_relation)
    * tempo     — BPM gap, judged against a "smooth" tolerance
    * energy    — direction and size of the energy change
"""
from __future__ import annotations

from typing import Optional

from .keydetect import harmonic_relation
from .models import Track, TransitionComment


def _tempo_assessment(a: Optional[float], b: Optional[float], tol: float) -> tuple[int, str]:
    if a is None or b is None:
        return 50, "BPM unknown — tempo match can't be judged."
    diff = b - a
    adiff = abs(diff)
    pct = adiff / a * 100 if a else 0
    arrow = "same tempo" if adiff < 0.5 else (f"+{diff:.0f} BPM" if diff > 0 else f"{diff:.0f} BPM")
    if adiff <= tol:
        return 95, f"{a:.0f}→{b:.0f} BPM ({arrow}) — beatmatch is easy."
    if pct <= 6:
        return 75, f"{a:.0f}→{b:.0f} BPM ({arrow}) — a small nudge, still mixable."
    if pct <= 12:
        return 50, f"{a:.0f}→{b:.0f} BPM ({arrow}) — noticeable jump; ride the pitch or use an effect."
    return 25, f"{a:.0f}→{b:.0f} BPM ({arrow}) — big tempo gap; consider a transition track."


def _energy_assessment(a: Optional[float], b: Optional[float], scale: int = 10) -> tuple[int, str]:
    if a is None or b is None:
        return 50, "Energy unknown."
    diff = b - a
    if abs(diff) < 0.6:
        return 85, f"Energy steady ({a:.0f}→{b:.0f}) — keeps the floor locked."
    if 0.6 <= diff <= 2.2:
        return 90, f"Energy rising ({a:.0f}→{b:.0f}) — nice build."
    if diff > 2.2:
        return 55, f"Energy jumps hard ({a:.0f}→{b:.0f}) — big lift, use where a peak is wanted."
    if -2.2 <= diff <= -0.6:
        return 70, f"Energy easing ({a:.0f}→{b:.0f}) — a gentle come-down."
    return 45, f"Energy drops sharply ({a:.0f}→{b:.0f}) — can kill momentum unless intentional."


def _rating(score: int) -> str:
    if score >= 85:
        return "great"
    if score >= 70:
        return "good"
    if score >= 55:
        return "ok"
    if score >= 40:
        return "risky"
    return "clash"


def score_transition(a: Track, b: Track, bpm_tol: float = 6, energy_scale: int = 10) -> TransitionComment:
    h_score, h_text = harmonic_relation(a.key_camelot, b.key_camelot)
    t_score, t_text = _tempo_assessment(a.bpm, b.bpm, bpm_tol)
    e_score, e_text = _energy_assessment(a.energy, b.energy, energy_scale)

    # Weight harmonic and tempo most heavily — they make or break a blend.
    overall = round(0.4 * h_score + 0.4 * t_score + 0.2 * e_score)
    rating = _rating(overall)

    lead = {
        "great": "Excellent fit.",
        "good": "Solid transition.",
        "ok": "Workable.",
        "risky": "Risky — mix with care.",
        "clash": "Likely clash.",
    }[rating]
    summary = f"{lead} {h_text.split('—')[0].strip()}; {t_text.split('—')[0].strip()}."

    return TransitionComment(
        from_id=a.id,
        to_id=b.id,
        score=overall,
        rating=rating,
        harmonic=h_text,
        tempo=t_text,
        energy=e_text,
        comment=summary,
    )


def score_sequence(tracks: list[Track], bpm_tol: float = 6, energy_scale: int = 10) -> list[TransitionComment]:
    """Score every adjacent pair in an ordered list of tracks."""
    out: list[TransitionComment] = []
    for a, b in zip(tracks, tracks[1:]):
        out.append(score_transition(a, b, bpm_tol, energy_scale))
    return out
