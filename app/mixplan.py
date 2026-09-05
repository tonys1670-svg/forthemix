"""Parse a plain-English *mix script* (explicit timecodes) into a structured plan.

Example line the parser understands:

    "mix track 4 into track 3 at track 3 1:24 / track 4 0:23"

meaning: while track 3 is playing and reaches 1:24, bring track 4 in from its
0:23 and blend there. Variants supported:

    "track 4 into track 3 at 3=1:24 4=0:23 crossfade 8s bass swap"
    "3 -> 4 at 1:24 / 0:23"        (out on 3, in on 4)

Only explicit timecodes are supported (1m24s / 1:24 / 84s). The parser is
deterministic — no LLM required — so scores/plan stay reproducible.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

# A timecode token must carry ':' , 'm' or 's' so it is never confused with a
# bare "track 3" number.
_TIME = r"(?:\d+:\d{1,2}(?:\.\d+)?|\d+m\d+s|\d+m\d+|\d+m|\d+s)"


class MixInstruction(BaseModel):
    from_index: int                 # 1-based position of the OUTGOING track
    to_index: int                   # 1-based position of the INCOMING track
    from_out_sec: Optional[float] = None   # cue on the outgoing track
    to_in_sec: Optional[float] = None      # cue on the incoming track
    crossfade_sec: Optional[float] = None  # blend length (None -> app default)
    technique: str = "crossfade"           # "crossfade" | "eq_bass_swap"


class MixWarning(BaseModel):
    kind: str                       # "tempo" | "key" | "parse" | "range"
    from_index: Optional[int] = None
    to_index: Optional[int] = None
    message: str
    options: list[str] = []


class MixPlan(BaseModel):
    track_ids: list[str] = []
    instructions: list[MixInstruction] = []
    warnings: list[MixWarning] = []


def parse_timecode(s) -> Optional[float]:
    """Parse '1m24s' / '1:24' / '84s' / '84' into seconds."""
    if s is None:
        return None
    s = str(s).strip().lower().replace(" ", "")
    if not s:
        return None
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except ValueError:
            return None
        return None
    m = re.fullmatch(r"(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s?)?", s)
    if m and (m.group(1) or m.group(2)):
        return (int(m.group(1)) if m.group(1) else 0) * 60 + (float(m.group(2)) if m.group(2) else 0.0)
    try:
        return float(s)
    except ValueError:
        return None


def _parse_line(line: str, n_tracks: int) -> tuple[Optional[MixInstruction], Optional[MixWarning]]:
    low = line.lower().strip()

    # Orientation: "A into B" = A incoming into B outgoing; "A -> B" = A out, B in.
    outgoing = incoming = None
    m = re.search(r"(?:mix\s+)?(?:track\s*)?(\d+)\s+into\s+(?:track\s*)?(\d+)", low)
    if m:
        incoming, outgoing = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"(?:track\s*)?(\d+)\s*(?:->|→|to)\s*(?:track\s*)?(\d+)", low)
        if m:
            outgoing, incoming = int(m.group(1)), int(m.group(2))
    if outgoing is None or incoming is None:
        return None, MixWarning(kind="parse", message=f"Couldn't read which tracks to mix from: “{line.strip()}”")

    if not (1 <= outgoing <= n_tracks and 1 <= incoming <= n_tracks):
        return None, MixWarning(kind="range", from_index=outgoing, to_index=incoming,
                                message=f"Track number out of range in: “{line.strip()}” (you have {n_tracks} tracks).")

    # Labelled times: "track 3 1:24" or "3=1:24"
    labelled: dict[int, float] = {}
    for num, tc in re.findall(r"(?:track\s*)?(\d+)\s*[=@:]?\s*(" + _TIME + r")", low):
        val = parse_timecode(tc)
        if val is not None:
            labelled[int(num)] = val

    if outgoing in labelled and incoming in labelled:
        from_out, to_in = labelled[outgoing], labelled[incoming]
    else:
        bare = [parse_timecode(t) for t in re.findall(_TIME, low)]
        from_out = bare[0] if len(bare) >= 1 else labelled.get(outgoing)
        to_in = bare[1] if len(bare) >= 2 else labelled.get(incoming)

    # Optional crossfade length ("crossfade 8s" / "over 8s" / "8s crossfade")
    cf = None
    cm = re.search(r"(?:crossfade|xfade|over)\s*(\d+(?:\.\d+)?)\s*s", low) or \
        re.search(r"(\d+(?:\.\d+)?)\s*s\s*(?:crossfade|xfade)", low)
    if cm:
        cf = float(cm.group(1))

    technique = "eq_bass_swap" if ("bass" in low or "eq" in low) else "crossfade"

    instr = MixInstruction(from_index=outgoing, to_index=incoming,
                           from_out_sec=from_out, to_in_sec=to_in,
                           crossfade_sec=cf, technique=technique)
    warn = None
    if from_out is None or to_in is None:
        warn = MixWarning(kind="parse", from_index=outgoing, to_index=incoming,
                          message=f"Missing a timecode in: “{line.strip()}” — using defaults where blank.")
    return instr, warn


def parse_script(text: str, n_tracks: int) -> tuple[list[MixInstruction], list[MixWarning]]:
    instructions: list[MixInstruction] = []
    warnings: list[MixWarning] = []
    for raw in (text or "").splitlines():
        if not raw.strip():
            continue
        instr, warn = _parse_line(raw, n_tracks)
        if instr:
            instructions.append(instr)
        if warn:
            warnings.append(warn)
    return instructions, warnings


def beatmatch_warnings(tracks: list, instructions: list[MixInstruction], warn_pct: float) -> list[MixWarning]:
    """Warn when a beatmatch would need a tempo change big enough to sound obvious.

    ``tracks`` is the ordered list of Track models (need .bpm / .key_camelot).
    Reference tempo is the first track's BPM (constant-tempo master).
    """
    from .keydetect import harmonic_relation

    out: list[MixWarning] = []
    ref = next((t.bpm for t in tracks if t.bpm), None)
    if not ref:
        return out
    for instr in instructions:
        i_in = instr.to_index - 1
        i_out = instr.from_index - 1
        if not (0 <= i_in < len(tracks) and 0 <= i_out < len(tracks)):
            continue
        b_in = tracks[i_in].bpm
        if b_in:
            pct = abs(ref / b_in - 1.0) * 100
            if pct > warn_pct:
                out.append(MixWarning(
                    kind="tempo", from_index=instr.from_index, to_index=instr.to_index,
                    message=(f"Beatmatching track {instr.to_index} ({b_in:.0f} BPM) to "
                             f"{ref:.0f} BPM is a {pct:.0f}% stretch — that can sound obvious."),
                    options=["Beatmatch anyway", "Straight crossfade (no tempo change)", "Pick a closer-tempo track"],
                ))
        # harmonic clash at the cue
        score, note = harmonic_relation(tracks[i_out].key_camelot, tracks[i_in].key_camelot)
        if score < 40:
            out.append(MixWarning(
                kind="key", from_index=instr.from_index, to_index=instr.to_index,
                message=f"Keys clash ({tracks[i_out].key_camelot}→{tracks[i_in].key_camelot}): {note}",
                options=["Mix anyway", "Use EQ bass-swap to hide the clash", "Pick a harmonically closer track"],
            ))
    return out
