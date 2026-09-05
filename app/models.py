"""Pydantic models shared across the API and analysis layers."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Track(BaseModel):
    """A single analysed track."""
    id: str                       # stable id (Drive file id, or hash of path)
    drive_id: Optional[str] = None
    name: str                     # display title
    artist: Optional[str] = None
    filename: str
    local_path: Optional[str] = None
    duration: Optional[float] = None      # seconds

    # analysis
    genre: Optional[str] = None
    bpm: Optional[float] = None
    key_camelot: Optional[str] = None     # e.g. "8A"
    key_name: Optional[str] = None        # e.g. "A minor"
    energy: Optional[float] = None        # 0..energy_scale
    loudness: Optional[float] = None      # dBFS-ish
    key_confidence: Optional[float] = None  # 0..1
    bpm_confidence: Optional[float] = None  # 0..1

    analyzed: bool = False
    peaks: Optional[list[float]] = None   # waveform peaks for the player
    error: Optional[str] = None


class TransitionComment(BaseModel):
    """Assessment of moving from one track to the next."""
    from_id: str
    to_id: str
    score: int                   # 0..100 overall fit
    rating: str                  # "great" | "good" | "ok" | "risky" | "clash"
    harmonic: str                # human note about key relationship
    tempo: str                   # human note about bpm relationship
    energy: str                  # human note about energy flow
    comment: str                 # one-line summary


class SavedMix(BaseModel):
    """A named, ordered set the user has saved for later."""
    id: str
    name: str
    description: Optional[str] = None
    track_ids: list[str] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CurationRequest(BaseModel):
    description: str
    target_minutes: Optional[int] = None
    track_ids: Optional[list[str]] = None   # restrict to a subset if provided


class CurationResult(BaseModel):
    track_ids: list[str]
    reasoning: str
    per_track_notes: dict[str, str] = {}
    used_ai: bool = True
