"""Export a finished mix as an M3U (extended) playlist."""
from __future__ import annotations

from pathlib import Path

from .models import Track


def build_m3u(tracks: list[Track]) -> str:
    lines = ["#EXTM3U"]
    for t in tracks:
        secs = int(t.duration) if t.duration else -1
        title = f"{t.artist} - {t.name}" if t.artist else t.name
        meta = []
        if t.bpm:
            meta.append(f"{t.bpm:.0f} BPM")
        if t.key_camelot:
            meta.append(t.key_camelot)
        suffix = f"  [{', '.join(meta)}]" if meta else ""
        lines.append(f"#EXTINF:{secs},{title}{suffix}")
        lines.append(t.local_path or t.filename)
    return "\n".join(lines) + "\n"


def write_m3u(tracks: list[Track], dest: Path) -> Path:
    dest = Path(dest)
    if dest.suffix.lower() not in (".m3u", ".m3u8"):
        dest = dest.with_suffix(".m3u8")
    dest.write_text(build_m3u(tracks), encoding="utf-8")
    return dest
