"""Background analysis job: download + analyse, resumable across restarts.

Progress and the work queue live in cache.db (see app/db.py), so a part-finished
analysis picks up where it left off when the app is relaunched. The job can be
paused, resumed and cancelled. Files the user hand-corrected are protected: on
re-analysis the ``user_edited`` fields are restored rather than overwritten.
"""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from typing import Optional


def preserve_user_edits(existing, fresh):
    """Copy user-corrected fields from ``existing`` onto a freshly analysed track.

    Re-analysis must never clobber a manual correction; corrected key/bpm keep
    full confidence. Returns ``fresh`` for convenience.
    """
    edits = list(existing.user_edited or [])
    if not edits:
        return fresh
    for f in edits:
        if hasattr(fresh, f):
            setattr(fresh, f, getattr(existing, f))
    fresh.user_edited = edits
    if "key_camelot" in edits:
        fresh.key_confidence = existing.key_confidence if existing.key_confidence is not None else 1.0
    if "bpm" in edits:
        fresh.bpm_confidence = existing.bpm_confidence if existing.bpm_confidence is not None else 1.0
    return fresh


class AnalysisJob:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._cancel = False
        self._session_start: Optional[float] = None
        self._session_done = 0

    # ---- state ---------------------------------------------------------- #
    def is_running(self) -> bool:
        from . import db
        return db.analysis_meta_get()["running"]

    def _eta(self, done: int, total: int) -> int:
        if not self._session_start or self._session_done <= 0 or total <= 0 or done >= total:
            return 0
        per = (time.time() - self._session_start) / self._session_done
        return int(max(0, (total - done) * per))

    def status(self) -> dict:
        from . import db
        meta = db.analysis_meta_get()
        done, total = db.analysis_counts()
        if total == 0:  # download phase / idle — fall back to the meta counters
            total = int(meta.get("total") or 0)
            done = int(meta.get("done") or 0)
        running = meta["running"]
        paused = meta["paused"]
        current = meta.get("current") or ""
        phase = (
            "paused" if (running and paused)
            else "analyzing" if running
            else "done" if (total and done >= total)
            else "idle"
        )
        return {
            "running": running,
            "paused": paused,
            "done": done,
            "total": total,
            "current": current,
            "eta_seconds": self._eta(done, total),
            "recent": db.analysis_recent(10),
            # extras kept for backward compatibility with the current UI
            "phase": phase,
            "message": current or (f"{done}/{total}" if total else ""),
        }

    @property
    def state(self) -> dict:
        return self.status()

    # ---- control -------------------------------------------------------- #
    def start(self, folder_id: str) -> bool:
        from . import db
        if self.is_running():
            return False
        db.analysis_reset()
        db.analysis_meta_set(
            running=1, paused=0, total=0, done=0,
            current="Preparing…", folder_id=folder_id, started_at=time.time(),
        )
        self._cancel = False
        self._session_start = time.time()
        self._session_done = 0
        self._thread = threading.Thread(target=self._run, args=(folder_id,), daemon=True)
        self._thread.start()
        return True

    def pause(self) -> bool:
        from . import db
        if not db.analysis_meta_get()["running"]:
            return False
        db.analysis_meta_set(paused=1)
        return True

    def resume(self) -> bool:
        from . import db
        db.analysis_meta_set(paused=0)
        if db.analysis_pending_count() > 0 and not (self._thread and self._thread.is_alive()):
            db.analysis_meta_set(running=1)
            self._cancel = False
            self._session_start = time.time()
            self._session_done = 0
            self._thread = threading.Thread(target=self._process_loop, daemon=True)
            self._thread.start()
        return True

    def cancel(self) -> bool:
        from . import db
        self._cancel = True
        db.analysis_meta_set(running=0, paused=0, current="")
        db.analysis_reset()
        return True

    def resume_if_pending(self) -> bool:
        """Called at startup — continue a run that was interrupted by a restart."""
        from . import db
        meta = db.analysis_meta_get()
        if meta["running"] and db.analysis_pending_count() > 0:
            self._cancel = False
            self._session_start = time.time()
            self._session_done = 0
            self._thread = threading.Thread(target=self._process_loop, daemon=True)
            self._thread.start()
            return True
        if meta["running"] and db.analysis_pending_count() == 0:
            db.analysis_meta_set(running=0, paused=0)  # clear a stale flag
        return False

    # ---- work ----------------------------------------------------------- #
    def _run(self, folder_id: str) -> None:
        from . import db, drive
        try:
            db.analysis_meta_set(running=1, paused=0, current="Listing Drive folder…")

            def dl_progress(idx: int, total: int, name: str) -> None:
                db.analysis_meta_set(current=f"Downloading {name}", total=total, done=idx - 1)

            files = drive.sync_folder(folder_id, progress=dl_progress)
            db.analysis_set_queue([
                {
                    "track_id": f["id"],
                    "name": f.get("name", "unknown"),
                    "local_path": f.get("local_path"),
                    "fingerprint": f.get("modifiedTime", ""),
                }
                for f in files
            ])
            db.analysis_meta_set(total=len(files), done=0, current="")
            self._process_loop()
        except Exception as exc:
            db.analysis_meta_set(running=0, paused=0, current=f"Failed: {exc}")
            traceback.print_exc()

    def _process_loop(self) -> None:
        from . import config, db
        settings = config.load_settings()
        if self._session_start is None:
            self._session_start = time.time()
        while True:
            if self._cancel:
                break
            if db.analysis_meta_get()["paused"]:
                time.sleep(0.2)
                continue
            item = db.analysis_next_pending()
            if not item:
                break
            db.analysis_meta_set(current=item.get("name") or "")
            status = self._process_one(
                item["track_id"], item.get("name") or "unknown",
                item.get("local_path"), item.get("fingerprint") or "", settings,
            )
            db.analysis_mark(item["seq"], status)
            done, _total = db.analysis_counts()
            db.analysis_meta_set(done=done)
            self._session_done += 1
        db.analysis_meta_set(running=0, paused=0, current="")

    def _process_one(self, track_id, name, local_path, fingerprint, settings) -> str:
        from . import db
        from .analysis import analyze_track
        from .models import Track

        existing = db.get_track(track_id)

        if not local_path or not Path(local_path).exists():
            db.upsert_track(
                Track(id=track_id, drive_id=track_id, name=name, filename=name,
                      error="Download failed", analyzed=False),
                fingerprint,
            )
            return "error"

        # Skip re-analysis when unchanged and already analysed.
        if existing and existing.analyzed and db.get_fingerprint(track_id) == fingerprint:
            return "cached"

        track = Track(id=track_id, drive_id=track_id, name=Path(name).stem,
                      filename=name, local_path=local_path)
        try:
            analyze_track(Path(local_path), track, settings)
        except Exception as exc:  # never let one bad file kill the run
            track.error = f"Analysis failed: {exc}"
            track.analyzed = False

        if existing:
            preserve_user_edits(existing, track)
        db.upsert_track(track, fingerprint)

        if track.analyzed:
            return "analysed"
        if track.error and (track.genre or track.artist):
            return "tags_only"
        return "error"


job = AnalysisJob()
