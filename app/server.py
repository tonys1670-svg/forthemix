"""FastAPI application: serves the UI and all analysis/curation endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, drive, export
from .curator import curate
from .jobs import job, render_job
from .mixplan import MixInstruction, beatmatch_warnings, parse_script
from .models import CurationRequest, SavedMix, Track
from .transitions import score_sequence, score_transition


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

app = FastAPI(title="ForTheMix")

FRONTEND_DIR = config.resource_path("frontend")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    try:
        job.resume_if_pending()  # continue an analysis interrupted by a restart
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Status & settings
# --------------------------------------------------------------------------- #
@app.get("/api/status")
def status() -> dict:
    settings = config.load_settings()
    try:
        from . import essentia_backend, stems
        essentia_ok = essentia_backend.is_available()
        stems_ok = stems.is_available()
    except Exception:
        essentia_ok = stems_ok = False
    return {
        "drive_connected": drive.is_connected(),
        "drive_folder_id": settings.get("drive_folder_id", ""),
        "drive_folder_name": settings.get("drive_folder_name", ""),
        "has_anthropic_key": config.has_anthropic_key(),
        "has_google_client": bool(settings.get("google_client_id")),
        "model": settings.get("anthropic_model"),
        "track_count": len(db.list_tracks()),
        "analysis_engine": settings.get("analysis_engine", "librosa"),
        "crossfade_seconds": settings.get("crossfade_seconds", 8),
        "mixes_dir": str(config.MIXES_DIR),
        "drive_mixes_folder_name": settings.get("drive_mixes_folder_name", ""),
        "essentia_available": essentia_ok,
        "stems_available": stems_ok,
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
    analysis_engine: Optional[str] = None
    essentia_genre_model: Optional[str] = None
    crossfade_seconds: Optional[int] = None
    stem_model: Optional[str] = None


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
    if body.analysis_engine in ("librosa", "essentia"):
        updates["analysis_engine"] = body.analysis_engine
    if body.essentia_genre_model is not None:
        updates["essentia_genre_model"] = body.essentia_genre_model.strip()
    if body.crossfade_seconds is not None:
        updates["crossfade_seconds"] = max(1, min(30, int(body.crossfade_seconds)))
    if body.stem_model:
        updates["stem_model"] = body.stem_model.strip()
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


@app.post("/api/drive/select-mixes-folder")
def select_mixes_folder(body: FolderIn) -> dict:
    config.save_settings({"drive_mixes_folder_id": body.id, "drive_mixes_folder_name": body.name})
    return {"drive_mixes_folder_id": body.id, "drive_mixes_folder_name": body.name}


class DriveSaveIn(BaseModel):
    track_ids: list[str]
    name: Optional[str] = "mix"
    copy_tracks: bool = False
    subfolder: Optional[str] = "project-mixes"   # find/create under the destination


@app.post("/api/drive/save-mix")
def drive_save_mix(body: DriveSaveIn) -> dict:
    if not drive.is_connected():
        raise HTTPException(status_code=400, detail="Not connected to Google Drive.")
    settings = config.load_settings()
    dest = settings.get("drive_mixes_folder_id")
    if not dest:
        raise HTTPException(
            status_code=400,
            detail="Choose a Drive destination folder for mixes in Settings first.",
        )
    tracks = [db.get_track(tid) for tid in body.track_ids]
    tracks = [t for t in tracks if t]
    if not tracks:
        raise HTTPException(status_code=400, detail="No tracks to save.")

    name = (body.name or "mix").strip() or "mix"
    try:
        parent = dest
        if body.subfolder:
            sub = drive.find_or_create_subfolder(dest, body.subfolder)
            parent = sub["id"]
        content = export.build_m3u(tracks).encode("utf-8")
        m3u = drive.upload_bytes(f"{name}.m3u8", content, parent, "audio/x-mpegurl")
        uploaded = [m3u.get("name")]
        if body.copy_tracks:
            for i, t in enumerate(tracks, 1):
                if t.local_path and Path(t.local_path).exists():
                    ext = Path(t.local_path).suffix or ".mp3"
                    up = drive.upload_local_file(t.local_path, parent, f"{i:02d} - {t.name}{ext}")
                    uploaded.append(up.get("name"))
    except drive.DriveError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        # Most likely an insufficient-scope token from before the read/write upgrade.
        raise HTTPException(
            status_code=400,
            detail=f"Drive upload failed ({exc}). If you connected before enabling "
                   f"write access, disconnect and reconnect Google Drive in Settings.",
        )
    return {"m3u_link": m3u.get("webViewLink"), "folder_id": parent, "uploaded": uploaded}


# --------------------------------------------------------------------------- #
# Library & analysis
# --------------------------------------------------------------------------- #
@app.get("/api/tracks")
def get_tracks(
    offset: int = 0,
    limit: Optional[int] = None,
    sort: str = "title",
    dir: str = "asc",
    q: Optional[str] = None,
    crate: str = "all",
    bpm_min: Optional[float] = None,
    bpm_max: Optional[float] = None,
) -> dict:
    """Paged/sorted/filtered library listing.

    With no parameters this returns every track (old behaviour) plus the
    total/offset/limit envelope, so existing callers keep working.
    """
    sort = sort if sort in ("title", "artist", "genre", "bpm", "key", "energy", "duration") else "title"
    direction = "desc" if str(dir).lower() == "desc" else "asc"
    crate = crate if crate in ("all", "unanalysed", "nogenre", "lowconf", "dupes") else "all"

    page, total = db.query_tracks(
        offset=max(0, offset), limit=limit, sort=sort, direction=direction,
        q=q, crate=crate, bpm_min=bpm_min, bpm_max=bpm_max,
    )
    # Peaks are large; omit from the list payload (fetched per-track on demand).
    slim = [t.model_dump(exclude={"peaks"}) for t in page]
    return {"tracks": slim, "total": total, "offset": max(0, offset), "limit": limit}


@app.get("/api/library/health")
def library_health() -> dict:
    return db.library_health()


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


def _apply_edits(t: Track, edits: dict) -> Track:
    """Apply user edits, record them in user_edited, and pin the relevant
    confidence to 1.0 so re-analysis leaves the correction alone."""
    edited = set(t.user_edited or [])
    for field_name, value in edits.items():
        setattr(t, field_name, value)
        edited.add(field_name)
    if "key_camelot" in edits:
        t.key_confidence = 1.0
    if "bpm" in edits:
        t.bpm_confidence = 1.0
    t.user_edited = sorted(edited)
    return t


@app.patch("/api/tracks/{track_id}")
def edit_track(track_id: str, body: TrackEdit) -> Track:
    t = db.get_track(track_id)
    if not t:
        raise HTTPException(status_code=404, detail="Track not found")
    _apply_edits(t, body.model_dump(exclude_none=True))
    db.upsert_track(t, db.get_fingerprint(track_id))
    return t


class BulkEdit(BaseModel):
    ids: list[str]
    genre: Optional[str] = None
    bpm: Optional[float] = None
    key_camelot: Optional[str] = None
    energy: Optional[float] = None
    name: Optional[str] = None
    artist: Optional[str] = None


@app.patch("/api/tracks")
def edit_tracks_bulk(body: BulkEdit) -> dict:
    """Apply the given fields to every listed id; returns the updated tracks."""
    edits = body.model_dump(exclude_none=True, exclude={"ids"})
    updated = []
    for tid in body.ids:
        t = db.get_track(tid)
        if not t:
            continue
        _apply_edits(t, edits)
        db.upsert_track(t, db.get_fingerprint(tid))
        updated.append(t.model_dump(exclude={"peaks"}))
    return {"updated": updated}


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


@app.post("/api/analyze/pause")
def analysis_pause() -> dict:
    return {"paused": job.pause(), "state": job.state}


@app.post("/api/analyze/resume")
def analysis_resume() -> dict:
    return {"resumed": job.resume(), "state": job.state}


@app.post("/api/analyze/cancel")
def analysis_cancel() -> dict:
    return {"cancelled": job.cancel(), "state": job.state}


@app.post("/api/cache/clear")
def clear_cache() -> dict:
    db.clear_all()
    return {"cleared": True}


# --------------------------------------------------------------------------- #
# Audio output device selection
# NOTE: these are declared BEFORE /api/audio/{track_id} so "devices"/"device"
# are not captured by the {track_id} path parameter.
# --------------------------------------------------------------------------- #
@app.get("/api/audio/devices")
def audio_devices() -> dict:
    from . import audiodev
    result = audiodev.list_output_devices()
    result["selected_id"] = config.load_settings().get("audio_device_id", "")
    return result


class AudioDeviceIn(BaseModel):
    id: str
    name: Optional[str] = ""


@app.post("/api/audio/device")
def set_audio_device(body: AudioDeviceIn) -> dict:
    config.save_settings({"audio_device_id": body.id, "audio_device_name": body.name or ""})
    return {
        "selected_id": body.id,
        "selected_name": body.name or "",
        "wired": False,
        "note": "Selection saved. Playback is not yet routed through Python to this device.",
    }


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
# Shared current mix (desktop <-> mobile companion) — persisted in cache.db.
# POST /api/transitions above stays the scoring endpoint, unchanged.
# --------------------------------------------------------------------------- #
@app.get("/api/mix")
def get_current_mix() -> dict:
    return {"track_ids": db.get_current_mix()}


class CurrentMixIn(BaseModel):
    track_ids: list[str]


@app.put("/api/mix")
def put_current_mix(body: CurrentMixIn) -> dict:
    db.set_current_mix(body.track_ids)
    return {"track_ids": body.track_ids}


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
# Save the finished mix to the Mixes folder on disk
# --------------------------------------------------------------------------- #
class SaveToDiskIn(BaseModel):
    track_ids: list[str]
    name: Optional[str] = "mix"
    copy_tracks: bool = False


@app.post("/api/export/save")
def export_save(body: SaveToDiskIn) -> dict:
    tracks = [db.get_track(tid) for tid in body.track_ids]
    tracks = [t for t in tracks if t]
    if not tracks:
        raise HTTPException(status_code=400, detail="No tracks to export.")
    result = export.save_mix_to_disk(tracks, body.name or "mix", body.copy_tracks)
    return result


# --------------------------------------------------------------------------- #
# Saved mixes (persist between sessions)
# --------------------------------------------------------------------------- #
@app.get("/api/mixes")
def list_mixes() -> dict:
    return {"mixes": [m.model_dump() for m in db.list_mixes()]}


class MixIn(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    track_ids: list[str] = []


@app.post("/api/mixes")
def save_mix(body: MixIn) -> SavedMix:
    now = _now()
    if body.id:
        existing = db.get_mix(body.id)
        created = existing.created_at if existing else now
        mix = SavedMix(id=body.id, name=body.name, description=body.description,
                       track_ids=body.track_ids, created_at=created, updated_at=now)
    else:
        mix = SavedMix(id=uuid.uuid4().hex, name=body.name, description=body.description,
                       track_ids=body.track_ids, created_at=now, updated_at=now)
    return db.save_mix(mix)


@app.get("/api/mixes/{mix_id}")
def get_mix(mix_id: str) -> SavedMix:
    mix = db.get_mix(mix_id)
    if not mix:
        raise HTTPException(status_code=404, detail="Mix not found")
    return mix


@app.delete("/api/mixes/{mix_id}")
def delete_mix(mix_id: str) -> dict:
    db.delete_mix(mix_id)
    return {"deleted": True}


# --------------------------------------------------------------------------- #
# Stem separation (optional / experimental)
# --------------------------------------------------------------------------- #
class StemIn(BaseModel):
    track_id: str
    two_stems: Optional[str] = None   # e.g. "vocals" for acapella/instrumental


@app.post("/api/stems")
def separate_stems(body: StemIn) -> dict:
    from . import stems

    if not stems.is_available():
        raise HTTPException(
            status_code=400,
            detail="Stem separation needs Demucs installed (pip install demucs). See README.",
        )
    t = db.get_track(body.track_id)
    if not t or not t.local_path or not Path(t.local_path).exists():
        raise HTTPException(status_code=404, detail="Track audio not available")
    model = config.load_settings().get("stem_model", "htdemucs")
    try:
        return stems.separate(Path(t.local_path), model=model, two_stems=body.two_stems)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Stem separation failed: {exc}")


# --------------------------------------------------------------------------- #
# Mix script — natural-language, timecoded transitions -> render / preview
# --------------------------------------------------------------------------- #
class MixScriptIn(BaseModel):
    text: str
    track_ids: list[str]


@app.post("/api/mixplan/parse")
def mixplan_parse(body: MixScriptIn) -> dict:
    tracks = [db.get_track(t) for t in body.track_ids]
    tracks = [t for t in tracks if t]
    instructions, warnings = parse_script(body.text, len(tracks))
    warn_pct = config.load_settings().get("beatmatch_warn_pct", 6)
    warnings = warnings + beatmatch_warnings(tracks, instructions, warn_pct)
    return {
        "track_ids": body.track_ids,
        "instructions": [i.model_dump() for i in instructions],
        "warnings": [w.model_dump() for w in warnings],
    }


class MixPreviewIn(BaseModel):
    track_ids: list[str]
    instruction: MixInstruction
    beatmatch: bool = True


@app.post("/api/mixplan/preview")
def mixplan_preview(body: MixPreviewIn):
    tracks = [db.get_track(t) for t in body.track_ids]
    fi, ti = body.instruction.from_index - 1, body.instruction.to_index - 1
    if not (0 <= fi < len(tracks) and 0 <= ti < len(tracks)) or not tracks[fi] or not tracks[ti]:
        raise HTTPException(status_code=400, detail="Transition refers to a track that isn't loaded.")
    a, b = tracks[fi], tracks[ti]
    for t in (a, b):
        if not (t.local_path and Path(t.local_path).exists()):
            raise HTTPException(status_code=400, detail=f"Audio for “{t.name}” isn't available locally.")
    settings = config.load_settings()
    sr = int(settings.get("mix_render_sr", 44100))
    cf = settings.get("crossfade_seconds", 8)
    import tempfile

    from .mixrender import render_segment_to_file
    dest = Path(tempfile.gettempdir()) / f"ftm_preview_{a.id}_{b.id}.wav"
    try:
        render_segment_to_file(a, b, body.instruction, dest, sr=sr, default_cf=cf, beatmatch=body.beatmatch)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Preview render failed: {exc}")
    return FileResponse(str(dest), media_type="audio/wav", filename="preview.wav")


class MixPlanIn(BaseModel):
    track_ids: list[str]
    instructions: list[MixInstruction] = []
    name: Optional[str] = "mix"
    beatmatch: bool = True


@app.post("/api/mixplan/render")
def mixplan_render(body: MixPlanIn) -> dict:
    tracks = [db.get_track(t) for t in body.track_ids]
    if any(t is None for t in tracks) or not tracks:
        raise HTTPException(status_code=400, detail="One or more tracks are missing.")
    for t in tracks:
        if not (t.local_path and Path(t.local_path).exists()):
            raise HTTPException(status_code=400, detail=f"Audio for “{t.name}” isn't available locally.")
    settings = config.load_settings()
    sr = int(settings.get("mix_render_sr", 44100))
    cf = settings.get("crossfade_seconds", 8)
    name = export._safe_name(body.name or "mix")
    started = render_job.start(tracks, body.instructions, name, sr, cf, body.beatmatch)
    return {"started": started, "state": render_job.state}


@app.get("/api/mixplan/render/status")
def mixplan_render_status() -> dict:
    return render_job.state


@app.get("/api/mixplan/render/file")
def mixplan_render_file():
    state = render_job.state
    path = state.get("file")
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail="No rendered mix available yet.")
    return FileResponse(path, media_type="audio/wav", filename=Path(path).name)


# --------------------------------------------------------------------------- #
# Frontend (mounted last so /api routes win)
# --------------------------------------------------------------------------- #
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
