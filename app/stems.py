"""Optional stem separation via Demucs (vocals / drums / bass / other).

Experimental and fully optional: Demucs is a large dependency (PyTorch + a
~300 MB model on first run) and benefits hugely from a GPU, so it is never a
hard requirement. ``is_available()`` reports whether Demucs imported; the API
endpoint only runs when it did. Separated stems are written under the app's
STEMS_DIR, grouped per source track.

See the stem-separation notes in the README for model choices and performance.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import STEMS_DIR


def is_available() -> bool:
    try:
        import demucs.separate  # noqa: F401
        return True
    except Exception:
        return False


def separate(source: Path, model: str = "htdemucs", two_stems: Optional[str] = None) -> dict:
    """Separate ``source`` into stems. Returns {"folder": path, "stems": [paths]}.

    ``two_stems`` (e.g. "vocals") produces just that stem plus an "everything
    else" stem — the fast path DJs use for acapellas/instrumentals.
    """
    import demucs.separate

    out_root = STEMS_DIR / source.stem
    out_root.mkdir(parents=True, exist_ok=True)

    args = ["-n", model, "-o", str(out_root)]
    if two_stems:
        args += ["--two-stems", two_stems]
    args.append(str(source))

    demucs.separate.main(args)

    stems = [str(p) for p in out_root.rglob("*.wav")]
    return {"folder": str(out_root), "stems": stems, "model": model}
