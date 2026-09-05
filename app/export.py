"""Export a finished mix as an M3U (extended) playlist."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .config import MIXES_DIR
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


def _safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]+', "_", (name or "mix").strip())
    return name[:120] or "mix"


def save_mix_to_disk(tracks: list[Track], name: str, copy_tracks: bool = False) -> dict:
    """Write the mix's M3U into the Mixes folder; optionally copy the audio too.

    Returns {"m3u": <path>, "folder": <path or None>} so the UI can tell the user
    exactly where the finished mix landed.
    """
    safe = _safe_name(name)
    m3u_path = MIXES_DIR / f"{safe}.m3u8"

    if copy_tracks:
        folder = MIXES_DIR / safe
        folder.mkdir(parents=True, exist_ok=True)
        copied: list[Track] = []
        for i, t in enumerate(tracks, 1):
            if t.local_path and Path(t.local_path).exists():
                ext = Path(t.local_path).suffix or ".mp3"
                target = folder / f"{i:02d} - {_safe_name(t.name)}{ext}"
                try:
                    shutil.copy2(t.local_path, target)
                except OSError:
                    target = Path(t.local_path)
                copy = t.model_copy()
                copy.local_path = str(target)
                copied.append(copy)
            else:
                copied.append(t)
        (folder / f"{safe}.m3u8").write_text(build_m3u(copied), encoding="utf-8")
        m3u_path.write_text(build_m3u(copied), encoding="utf-8")
        return {"m3u": str(m3u_path), "folder": str(folder)}

    m3u_path.write_text(build_m3u(tracks), encoding="utf-8")
    return {"m3u": str(m3u_path), "folder": None}
