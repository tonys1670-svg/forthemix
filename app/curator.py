"""AI playlist curation via the Claude API, with a rule-based fallback.

The user describes a vibe ("sunset rooftop, warm house, slowly building, ~60
min"); Claude receives the analysed library as compact JSON and returns an
ordered set of track ids plus reasoning. If no API key is configured (or the
call fails) we fall back to a deterministic harmonic/energy ordering so the
feature still works offline.
"""
from __future__ import annotations

import json
from typing import Optional

from . import config
from .keydetect import harmonic_relation
from .models import CurationResult, Track

_SYSTEM = """You are an expert DJ and music curator. You build harmonically
coherent, well-paced DJ sets from a fixed library of tracks. You must ONLY use
tracks from the library provided — never invent tracks. You understand Camelot
harmonic mixing, BPM beatmatching and energy arcs. Respond with STRICT JSON only."""


def _track_brief(t: Track) -> dict:
    return {
        "id": t.id,
        "title": t.name,
        "artist": t.artist or "",
        "genre": t.genre or "unknown",
        "bpm": t.bpm,
        "key": t.key_camelot,
        "energy": t.energy,
        "duration_sec": t.duration,
    }


def _estimate_count(target_minutes: Optional[int], tracks: list[Track]) -> Optional[int]:
    if not target_minutes:
        return None
    avg = [t.duration for t in tracks if t.duration]
    avg_sec = sum(avg) / len(avg) if avg else 240.0
    return max(1, round(target_minutes * 60 / avg_sec))


def curate_with_ai(
    description: str,
    tracks: list[Track],
    target_minutes: Optional[int] = None,
) -> CurationResult:
    import anthropic

    api_key = config.get_anthropic_key()
    if not api_key:
        raise RuntimeError("No Anthropic API key set.")

    model = config.load_settings().get("anthropic_model", "claude-opus-4-8")
    library = [_track_brief(t) for t in tracks if t.analyzed]
    want = _estimate_count(target_minutes, tracks)
    length_hint = (
        f"Aim for about {want} tracks (~{target_minutes} minutes)."
        if want else "Choose an appropriate number of tracks."
    )

    user_msg = (
        f"LIBRARY (JSON array of available tracks):\n{json.dumps(library)}\n\n"
        f"PLAYLIST BRIEF: {description}\n{length_hint}\n\n"
        "Select and ORDER tracks from the library to match the brief. Favour smooth "
        "harmonic (Camelot) and BPM transitions and a sensible energy arc. "
        'Respond as STRICT JSON: {"track_ids": [..in play order..], '
        '"reasoning": "2-4 sentences on the overall arc", '
        '"per_track_notes": {"<id>": "why it is here / how it connects"}}.'
    )

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
    data = _extract_json(text)

    valid_ids = {t.id for t in tracks}
    ordered = [tid for tid in data.get("track_ids", []) if tid in valid_ids]
    if not ordered:
        raise RuntimeError("AI returned no usable track selection.")
    return CurationResult(
        track_ids=ordered,
        reasoning=data.get("reasoning", ""),
        per_track_notes={k: v for k, v in data.get("per_track_notes", {}).items() if k in valid_ids},
        used_ai=True,
    )


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def curate_rule_based(
    description: str,
    tracks: list[Track],
    target_minutes: Optional[int] = None,
) -> CurationResult:
    """Deterministic fallback: filter by keywords, then greedily chain by harmony."""
    pool = [t for t in tracks if t.analyzed]
    desc = description.lower()

    # Light keyword filtering on genre.
    genre_hits = [t for t in pool if t.genre and t.genre.lower() in desc]
    if len(genre_hits) >= 3:
        pool = genre_hits

    # Energy-direction hint.
    ascending = any(w in desc for w in ("build", "rising", "warm up", "warmup", "peak"))
    descending = any(w in desc for w in ("wind down", "chill", "come down", "closing", "sunset"))

    if not pool:
        return CurationResult(track_ids=[], reasoning="No analysed tracks to curate from.", used_ai=False)

    # Start from the lowest-energy track when building up, else highest.
    pool_sorted = sorted(pool, key=lambda t: (t.energy or 0))
    current = pool_sorted[0] if ascending or not descending else pool_sorted[-1]

    remaining = [t for t in pool if t.id != current.id]
    order = [current]
    while remaining:
        nxt = max(
            remaining,
            key=lambda t: harmonic_relation(current.key_camelot, t.key_camelot)[0]
            - abs((t.bpm or 0) - (current.bpm or 0)) * 0.5,
        )
        order.append(nxt)
        remaining.remove(nxt)
        current = nxt

    want = _estimate_count(target_minutes, tracks)
    if want:
        order = order[:want]

    return CurationResult(
        track_ids=[t.id for t in order],
        reasoning=(
            "Built offline (no AI key): filtered by your description, then chained "
            "tracks for the smoothest harmonic and tempo flow"
            + (", building energy upward." if ascending else ".")
        ),
        per_track_notes={},
        used_ai=False,
    )


def curate(description: str, tracks: list[Track], target_minutes: Optional[int] = None) -> CurationResult:
    """Use Claude when a key is present, else fall back to rule-based ordering."""
    if config.has_anthropic_key():
        try:
            return curate_with_ai(description, tracks, target_minutes)
        except Exception as exc:
            result = curate_rule_based(description, tracks, target_minutes)
            result.reasoning = f"(AI unavailable: {exc}) " + result.reasoning
            return result
    return curate_rule_based(description, tracks, target_minutes)
