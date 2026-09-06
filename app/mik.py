"""Read Mixed In Key / DJ metadata from a track's ID3 tags (and, as a fallback,
its filename).

Mixed In Key's "Update ID3 tags" writes the analysed values into the file:
  * key      -> the TKEY frame (Camelot like "8A", Open Key like "1m", or a
                musical key like "Abm"), and often into the Comment/Title too
  * BPM      -> the TBPM frame
  * energy   -> the Comment (COMM) as "Energy 7", sometimes the Grouping
This module normalises all of those to the app's Camelot + 0..10 energy so the
user's own MIK analysis becomes the source of truth, instead of re-deriving
(less accurately) with librosa.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .keydetect import camelot_from_key

# Valid Camelot code, e.g. 8A / 12B
_CAMELOT_RE = re.compile(r"^\s*(1[0-2]|[1-9])\s*([abAB])\s*$")
# Open Key notation, e.g. 1m / 12d  (m = minor ring, d = major ring)
_OPENKEY_RE = re.compile(r"^\s*(1[0-2]|[1-9])\s*([mdMD])\s*$")
# Musical key, e.g. Abm, F#m, Am, C, F#, "A minor"
_MUSICAL_RE = re.compile(r"^\s*([A-Ga-g])([#b♯♭]?)\s*(m|min|minor|maj|major)?\s*$")

# Open Key -> Camelot: Open Key "1m" == Camelot "6A"; each step maps 1:1 with a
# +5 (mod 12) offset. Minor(m)->A ring, major(d)->B ring.
def _openkey_to_camelot(num: int, letter: str) -> str:
    cam_num = ((num + 4) % 12) + 1  # 1m->6A, 2m->7A, ...
    ring = "A" if letter.lower() == "m" else "B"
    return f"{cam_num}{ring}"


def normalize_key(raw: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Return (camelot, key_name) from any common key string, or (None, None)."""
    if not raw:
        return None, None
    s = str(raw).strip()
    m = _CAMELOT_RE.match(s)
    if m:
        return f"{int(m.group(1))}{m.group(2).upper()}", None
    m = _OPENKEY_RE.match(s)
    if m:
        return _openkey_to_camelot(int(m.group(1)), m.group(2)), None
    m = _MUSICAL_RE.match(s)
    if m:
        root = m.group(1).upper() + m.group(2).replace("♯", "#").replace("♭", "b")
        scale = "minor" if (m.group(3) or "").lower().startswith("min") or (m.group(3) or "").lower() == "m" else "major"
        cam, name = camelot_from_key(root, scale)
        return cam, name
    return None, None


def _energy_from_text(text: str) -> Optional[float]:
    if not text:
        return None
    m = re.search(r"energy\s*[-:]?\s*(\d{1,2})", text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        return float(min(10, max(0, val)))
    return None


def read_tags(path: Path) -> dict:
    """Read the full ID3/metadata frames we care about, best-effort."""
    out: dict = {}
    try:
        from mutagen import File as MutagenFile

        mf = MutagenFile(str(path))
        if mf is None:
            return out
        tags = getattr(mf, "tags", None)
        if not tags:
            return out

        def first(*keys):
            for k in keys:
                try:
                    v = tags.get(k)
                except Exception:
                    v = None
                if v:
                    return str(v[0]) if isinstance(v, list) else str(v)
            return None

        out["key"] = first("TKEY", "key", "initialkey", "INITIALKEY")
        out["bpm"] = first("TBPM", "bpm")
        out["genre"] = first("TCON", "genre")
        out["title"] = first("TIT2", "title")
        out["artist"] = first("TPE1", "artist")
        out["grouping"] = first("TIT1", "GRP1", "grouping")

        # Comments (COMM frames) — MIK often puts "Energy N" here.
        comments = []
        try:
            for key in tags.keys():
                if str(key).startswith("COMM"):
                    fr = tags.get(key)
                    comments.append(str(getattr(fr, "text", fr)))
        except Exception:
            pass
        try:
            easy = tags.get("comment")
            if easy:
                comments.append(str(easy[0]) if isinstance(easy, list) else str(easy))
        except Exception:
            pass
        out["comment"] = " ".join(comments)
    except Exception:
        pass
    return out


def _from_filename(name: str) -> dict:
    """Pull key/BPM out of filenames like '... 7A 121', 'd#m130', '126 Bpm'."""
    out: dict = {}
    stem = Path(name).stem
    # explicit "<camelot> <bpm>" e.g. "7A 121"
    m = re.search(r"\b(1[0-2]|[1-9])([ABab])\b(?:\s+(\d{2,3}))?", stem)
    if m:
        out["key"] = f"{int(m.group(1))}{m.group(2).upper()}"
        if m.group(3):
            out["bpm"] = m.group(3)
    # musical prefix like "d#m130"
    m = re.match(r"^\s*([A-Ga-g][#b]?m?)\s?(\d{2,3})\b", stem)
    if m and "key" not in out:
        out["key"] = m.group(1)
        out["bpm"] = m.group(2)
    # a standalone bpm like "126 Bpm"
    if "bpm" not in out:
        m = re.search(r"\b(\d{2,3})\s*bpm\b", stem, re.IGNORECASE)
        if m:
            out["bpm"] = m.group(1)
    return out


def read(path: Path) -> dict:
    """Return normalised MIK/tag metadata: any of
    {key_camelot, key_name, bpm, energy, genre, title, artist}."""
    tags = read_tags(path)
    fn = _from_filename(path.name)

    result: dict = {}

    cam, name = normalize_key(tags.get("key"))
    if not cam:
        cam, name = normalize_key(fn.get("key"))
    if cam:
        result["key_camelot"] = cam
        if name:
            result["key_name"] = name

    bpm_raw = tags.get("bpm") or fn.get("bpm")
    if bpm_raw:
        try:
            bpm = float(str(bpm_raw).strip())
            if 40 <= bpm <= 260:
                result["bpm"] = round(bpm, 1)
        except ValueError:
            pass

    energy = _energy_from_text(tags.get("comment", "")) or _energy_from_text(tags.get("grouping", ""))
    if energy is not None:
        result["energy"] = energy

    if tags.get("genre"):
        result["genre"] = tags["genre"]
    if tags.get("title"):
        result["title"] = tags["title"]
    if tags.get("artist"):
        result["artist"] = tags["artist"]

    return result


def apply(path: Path, track) -> list[str]:
    """Overlay MIK/tag values onto a Track (authoritative over librosa).

    Sets key/bpm confidence to 1.0 for values that came from tags. Returns the
    list of fields that were sourced from MIK/tags (for the UI to badge).
    """
    data = read(Path(path))
    sourced: list[str] = []
    if data.get("key_camelot"):
        track.key_camelot = data["key_camelot"]
        track.key_name = data.get("key_name") or track.key_name
        track.key_confidence = 1.0
        sourced.append("key_camelot")
    if data.get("bpm"):
        track.bpm = data["bpm"]
        track.bpm_confidence = 1.0
        sourced.append("bpm")
    if data.get("energy") is not None:
        track.energy = data["energy"]
        sourced.append("energy")
    if data.get("genre") and not track.genre:
        track.genre = data["genre"]
    if data.get("artist") and not track.artist:
        track.artist = data["artist"]
    return sourced
