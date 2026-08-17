"""Background job runner for folder sync + analysis (keeps the UI responsive)."""
from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class JobState:
    running: bool = False
    phase: str = "idle"          # "idle" | "downloading" | "analyzing" | "done" | "error"
    current: int = 0
    total: int = 0
    message: str = ""
    error: Optional[str] = None
    analyzed_ids: list[str] = field(default_factory=list)

    def snapshot(self) -> dict:
        return asdict(self)


class AnalysisJob:
    def __init__(self) -> None:
        self._state = JobState()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    @property
    def state(self) -> dict:
        with self._lock:
            return self._state.snapshot()

    def _set(self, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self._state, k, v)

    def is_running(self) -> bool:
        with self._lock:
            return self._state.running

    def start(self, folder_id: str) -> bool:
        if self.is_running():
            return False
        self._set(
            running=True, phase="starting", current=0, total=0,
            message="Preparing…", error=None, analyzed_ids=[],
        )
        self._thread = threading.Thread(target=self._run, args=(folder_id,), daemon=True)
        self._thread.start()
        return True

    def _run(self, folder_id: str) -> None:
        # Imported lazily so a missing optional dep can't break app import.
        from . import config, db, drive
        from .analysis import analyze_file
        from .models import Track

        settings = config.load_settings()
        energy_scale = int(settings.get("energy_scale", 10))
        try:
            self._set(phase="downloading", message="Listing Drive folder…")

            def dl_progress(idx: int, total: int, name: str) -> None:
                self._set(current=idx, total=total, message=f"Downloading {name}")

            files = drive.sync_folder(folder_id, progress=dl_progress)
            self._set(phase="analyzing", current=0, total=len(files), message="Analysing…")

            for idx, f in enumerate(files, 1):
                name = f.get("name", "unknown")
                self._set(current=idx, message=f"Analysing {name}")
                local_path = f.get("local_path")
                track_id = f["id"]
                fingerprint = f.get("modifiedTime", "")

                if not local_path or not Path(local_path).exists():
                    db.upsert_track(
                        Track(id=track_id, drive_id=track_id, name=name, filename=name,
                              error=f.get("download_error", "Download failed"), analyzed=False),
                        fingerprint,
                    )
                    continue

                # Skip re-analysis when unchanged and already analysed.
                if db.get_fingerprint(track_id) == fingerprint:
                    existing = db.get_track(track_id)
                    if existing and existing.analyzed:
                        self._state.analyzed_ids.append(track_id)
                        continue

                track = Track(
                    id=track_id, drive_id=track_id, name=Path(name).stem,
                    filename=name, local_path=local_path,
                )
                try:
                    analyze_file(Path(local_path), track, energy_scale)
                except Exception as exc:  # never let one bad file kill the run
                    track.error = f"Analysis failed: {exc}"
                    track.analyzed = False
                db.upsert_track(track, fingerprint)
                if track.analyzed:
                    self._state.analyzed_ids.append(track_id)

            self._set(phase="done", running=False, message=f"Done — {len(files)} tracks processed.")
        except Exception as exc:
            self._set(
                phase="error", running=False,
                error=str(exc), message="Failed: " + str(exc),
            )
            traceback.print_exc()


job = AnalysisJob()
