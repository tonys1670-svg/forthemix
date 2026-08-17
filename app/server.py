"""FastAPI application: serves the UI and all analysis/curation endpoints."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, drive, export
from .curator import curate
from .jobs import job
from .models import CurationRequest, Track
from .transitions import score_sequence, score_transition

app = FastAPI(title="ForTheMix")

FRONTEND_DIR = config.resource_path("frontend")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


# --------------------------------------------------------------------------- #
# Status & settings
# --------------------------------------------------------------------------- #
@app.get("/api/status")
def status() -> dict:
    settings = config.load_settings()
    return {
        "drive_connected": drive.is_connected(),
        "drive_folder_id": settings.get("drive_folder_id", ""),
        "drive_folder_name": settings.get("drive_folder_name", ""),
        "has_anthropic_key": config.has_anthropic_key(),
        "has_google_client": bool(settings.get("google_client_id")),
        "model": settings.get("anthropic_model"),
        "track_count": len(db.list_tracks()),
    }


@app.get("/api/settings")
def get_settings() -> dict:
    s = config.load_settings()
    # Never return the client secret to the UI.
    s = dict(s)
    s["google_client_secret_set"] = bool(s.pop("google_client_secret", ""))
    return s


class SettingsIn(BaseModel):
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    anthropic_model: Optional[str] = None
    target_bpm_tolerance: Optional[int] = None


@app.post("/api/settings")
def update_settings(body: SettingsIn) -> dict:
    updates: dict = {}
    if body.google_client_id is not None:
        updates["google_client_id"] = body.google_client_id.strip()
    if body.google_client_secret:  # only overwrite when a new value is provided
        updates["google_client_secret"] = body.google_client_secret.strip()
    if body.anthropic_model:
        updates["anthropic_model"] = body.anthropic_model.strip()
    if body.target_bpm_tolerance is not None:
        updates["target_bpm_tolerance"] = int(body.target_bpm_tolerance)
    if updates:
        config.save_settings(updates)
    if body.anthropic_api_key is not None and body.anthropic_api_key.strip():
        config.set_anthropic_key(body.anthropic_api_key)
    return get_settings()


# --------------------------------------------------------------------------- #
# Google Drive
# --------------------------------------------------------------------------- #
@app.post("/api/drive/connect")
def drive_connect() -> dict:
    try:
        drive.start_auth()
    except drive.DriveError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Google sign-in failed: {exc}")
    return {"connected": drive.is_connected()}


@app.post("/api/drive/disconnect")
def drive_disconnect() -> dict:
    drive.disconnect()
    return {"connected": False}


@app.get("/api/drive/folders")
def drive_folders(parent: Optional[str] = None) -> dict:
    try:
        return {"folders": drive.list_folders(parent)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/drive/search")
def drive_search(name: str) -> dict:
    try:
        return {"folders": drive.find_folder_by_name(name)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class FolderIn(BaseModel):
    id: str
    name: str = ""


@app.post("/api/drive/select-folder")
def select_folder(body: FolderIn) -> dict:
    config.save_settings({"drive_folder_id": body.id, "drive_folder_name": body.name})
    return {"drive_folder_id": body.id, "drive_folder_name": body.name}


# --------------------------------------------------------------------------- #
# Library & analysis
# --------------------------------------------------------------------------- #
@app.get("/api/tracks")
def get_tracks() -> dict:
    tracks = db.list_tracks()
    # Peaks are large; omit from the list payload (fetched per-track on demand).
    slim = [t.model_dump(exclude={"peaks"}) for t in tracks]
    return {"tracks": slim}


@app.get("/api/tracks/{track_id}")
def get_track(track_id: str) -> Track:
    t = db.get_track(track_id)
    if not t:
        raise HTTPException(status_code=404, detail="Track not found")
    return t


class TrackEdit(BaseModel):
    genre: Optional[str] = None
    bpm: Optional[float] = None
    key_camelot: Optional[str] = None
    energy: Optional[float] = None
    name: Optional[str] = None
    artist: Optional[str] = None


@app.patch("/api/tracks/{track_id}")
def edit_track(track_id: str, body: TrackEdit) -> Track:
    t = db.get_track(track_id)
    if not t:
        raise HTTPException(status_code=404, detail="Track not found")
    for field_name, value in body.model_dump(exclude_none=True).items():
        setattr(t, field_name, value)
    db.upsert_track(t, db.get_fingerprint(track_id))
    return t


@app.post("/api/analyze")
def start_analysis() -> dict:
    settings = config.load_settings()
    folder_id = settings.get("drive_folder_id")
    if not folder_id:
        raise HTTPException(status_code=400, detail="No Drive folder selected.")
    if not drive.is_connected():
        raise HTTPException(status_code=400, detail="Not connected to Google Drive.")
    started = job.start(folder_id)
    return {"started": started, "state": job.state}


@app.get("/api/analyze/status")
def analysis_status() -> dict:
    return job.state


@app.post("/api/cache/clear")
def clear_cache() -> dict:
    db.clear_all()
    return {"cleared": True}


# --------------------------------------------------------------------------- #
# Audio streaming for the player
# --------------------------------------------------------------------------- #
@app.get("/api/audio/{track_id}")
def stream_audio(track_id: str):
    t = db.get_track(track_id)
    if not t or not t.local_path or not Path(t.local_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not available")
    return FileResponse(t.local_path, filename=t.filename)


# --------------------------------------------------------------------------- #
# Transitions
# --------------------------------------------------------------------------- #
class SequenceIn(BaseModel):
    track_ids: list[str]


@app.post("/api/transitions")
def transitions(body: SequenceIn) -> dict:
    tracks = [db.get_track(tid) for tid in body.track_ids]
    tracks = [t for t in tracks if t]
    tol = config.load_settings().get("target_bpm_tolerance", 6)
    comments = score_sequence(tracks, bpm_tol=tol)
    return {"transitions": [c.model_dump() for c in comments]}


class PairIn(BaseModel):
    from_id: str
    to_id: str


@app.post("/api/transition")
def transition_pair(body: PairIn) -> dict:
    a, b = db.get_track(body.from_id), db.get_track(body.to_id)
    if not a or not b:
        raise HTTPException(status_code=404, detail="Track not found")
    tol = config.load_settings().get("target_bpm_tolerance", 6)
    return score_transition(a, b, bpm_tol=tol).model_dump()


# --------------------------------------------------------------------------- #
# AI curation
# --------------------------------------------------------------------------- #
@app.post("/api/curate")
def curate_playlist(body: CurationRequest) -> dict:
    tracks = db.list_tracks()
    if body.track_ids:
        allowed = set(body.track_ids)
        tracks = [t for t in tracks if t.id in allowed]
    tracks = [t for t in tracks if t.analyzed]
    if not tracks:
        raise HTTPException(status_code=400, detail="No analysed tracks to curate from.")
    result = curate(body.description, tracks, body.target_minutes)
    return result.model_dump()


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
class ExportIn(BaseModel):
    track_ids: list[str]
    filename: Optional[str] = "mix"


@app.post("/api/export/m3u")
def export_m3u(body: ExportIn):
    tracks = [db.get_track(tid) for tid in body.track_ids]
    tracks = [t for t in tracks if t]
    if not tracks:
        raise HTTPException(status_code=400, detail="No tracks to export.")
    content = export.build_m3u(tracks)
    fname = (body.filename or "mix").strip() or "mix"
    if not fname.lower().endswith((".m3u", ".m3u8")):
        fname += ".m3u8"
    return Response(
        content=content,
        media_type="audio/x-mpegurl",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# --------------------------------------------------------------------------- #
# Frontend (mounted last so /api routes win)
# --------------------------------------------------------------------------- #
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
