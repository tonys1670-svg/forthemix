"""Google Drive OAuth and audio-file download.

The app authenticates as the user (installed-app OAuth flow) using a Google
OAuth client id/secret entered on the Settings screen. Only read-only Drive
scope is requested. Audio files from the nominated folder are downloaded into
the local audio cache and only re-downloaded when their Drive ``modifiedTime``
changes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from . import config

# readonly: browse/list/download the nominated library folder.
# drive.file: create files/folders the app makes (used to upload finished mixes
# into your Mixes destination folder). Least-privilege for read + write-back.
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
]

_AUDIO_MIME_PREFIXES = ("audio/",)
_AUDIO_EXTS = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".aiff", ".aif", ".ogg", ".wma")


class DriveError(RuntimeError):
    pass


def _load_credentials():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    if not config.GOOGLE_TOKEN_PATH.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(config.GOOGLE_TOKEN_PATH), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        config.GOOGLE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def is_connected() -> bool:
    try:
        creds = _load_credentials()
        return bool(creds and creds.valid)
    except Exception:
        return False


def start_auth() -> None:
    """Run the installed-app OAuth flow (opens a browser, spins a local server)."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings = config.load_settings()
    client_id = settings.get("google_client_id", "").strip()
    client_secret = settings.get("google_client_secret", "").strip()
    if not client_id or not client_secret:
        raise DriveError("Google OAuth client id/secret not set. Add them in Settings.")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    config.GOOGLE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")


def disconnect() -> None:
    try:
        config.GOOGLE_TOKEN_PATH.unlink()
    except FileNotFoundError:
        pass


def _service():
    from googleapiclient.discovery import build

    creds = _load_credentials()
    if not creds or not creds.valid:
        raise DriveError("Not connected to Google Drive. Sign in from Settings.")
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_folders(parent: Optional[str] = None) -> list[dict]:
    """List sub-folders (for a folder picker). Root if ``parent`` is None."""
    svc = _service()
    q = "mimeType='application/vnd.google-apps.folder' and trashed=false"
    q += f" and '{parent}' in parents" if parent else " and 'root' in parents"
    resp = svc.files().list(
        q=q, fields="files(id,name)", orderBy="name", pageSize=200
    ).execute()
    return resp.get("files", [])


def find_folder_by_name(name: str) -> list[dict]:
    svc = _service()
    safe = name.replace("'", "\\'")
    q = (
        "mimeType='application/vnd.google-apps.folder' and trashed=false "
        f"and name contains '{safe}'"
    )
    resp = svc.files().list(q=q, fields="files(id,name)", pageSize=50).execute()
    return resp.get("files", [])


def _is_audio(f: dict) -> bool:
    mime = f.get("mimeType", "")
    if any(mime.startswith(p) for p in _AUDIO_MIME_PREFIXES):
        return True
    return Path(f.get("name", "")).suffix.lower() in _AUDIO_EXTS


def list_audio_files(folder_id: str) -> list[dict]:
    """List audio files directly inside ``folder_id``."""
    svc = _service()
    files: list[dict] = []
    page_token = None
    while True:
        resp = svc.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id,name,mimeType,modifiedTime,size)",
            pageSize=200,
            pageToken=page_token,
        ).execute()
        files.extend(f for f in resp.get("files", []) if _is_audio(f))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def download_file(file_id: str, name: str) -> Path:
    """Download a Drive file into the local audio cache, return its path."""
    from googleapiclient.http import MediaIoBaseDownload

    svc = _service()
    dest = config.AUDIO_DIR / f"{file_id}__{name}"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    request = svc.files().get_media(fileId=file_id)
    with open(dest, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    return dest


def find_or_create_subfolder(parent_id: str, name: str) -> dict:
    """Return an existing sub-folder named ``name`` under ``parent_id``, or create it."""
    svc = _service()
    safe = name.replace("'", "\\'")
    q = (
        "mimeType='application/vnd.google-apps.folder' and trashed=false "
        f"and name='{safe}' and '{parent_id}' in parents"
    )
    existing = svc.files().list(q=q, fields="files(id,name)", pageSize=1).execute().get("files", [])
    if existing:
        return existing[0]
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]}
    return svc.files().create(body=meta, fields="id,name").execute()


def upload_bytes(name: str, data: bytes, parent_id: str, mime: str = "application/octet-stream") -> dict:
    """Upload in-memory bytes as a new Drive file inside ``parent_id``."""
    import io

    from googleapiclient.http import MediaIoBaseUpload

    svc = _service()
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
    meta = {"name": name, "parents": [parent_id]}
    return svc.files().create(
        body=meta, media_body=media, fields="id,name,webViewLink"
    ).execute()


def upload_local_file(path: str, parent_id: str, name: Optional[str] = None) -> dict:
    """Upload a local file into ``parent_id``."""
    from googleapiclient.http import MediaFileUpload

    svc = _service()
    p = Path(path)
    media = MediaFileUpload(str(p), resumable=True)
    meta = {"name": name or p.name, "parents": [parent_id]}
    return svc.files().create(
        body=meta, media_body=media, fields="id,name,webViewLink"
    ).execute()


def sync_folder(folder_id: str, progress: Optional[Callable[[int, int, str], None]] = None) -> list[dict]:
    """Download all audio files from a folder; return their metadata with local_path."""
    files = list_audio_files(folder_id)
    total = len(files)
    out: list[dict] = []
    for idx, f in enumerate(files, 1):
        if progress:
            progress(idx, total, f.get("name", ""))
        try:
            path = download_file(f["id"], f["name"])
            f["local_path"] = str(path)
        except Exception as exc:
            f["local_path"] = None
            f["download_error"] = str(exc)
        out.append(f)
    return out
