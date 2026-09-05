"""Application paths, settings, and local (encrypted) credential storage.

All user data lives under a per-user application-data directory so the packaged
Windows app never needs write access to its install location:

    %APPDATA%\\ForTheMix\\
        settings.json          non-secret preferences
        secrets.enc            Anthropic API key, encrypted at rest
        key.bin                local encryption key (machine-bound file)
        google_token.json      cached Google OAuth token
        cache.db               SQLite analysis cache
        audio/                 downloaded audio files
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

from . import APP_NAME


def _data_dir() -> Path:
    """Return the per-user writable data directory for this OS."""
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA_DIR = _data_dir()
AUDIO_DIR = DATA_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Finished mixes (M3U playlists, optional copied tracks) are written here.
MIXES_DIR = DATA_DIR / "mixes"
MIXES_DIR.mkdir(parents=True, exist_ok=True)

# Separated stems (vocals / instrumental etc.), grouped per source track.
STEMS_DIR = DATA_DIR / "stems"
STEMS_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_PATH = DATA_DIR / "settings.json"
SECRETS_PATH = DATA_DIR / "secrets.enc"
KEYFILE_PATH = DATA_DIR / "key.bin"
GOOGLE_TOKEN_PATH = DATA_DIR / "google_token.json"
DB_PATH = DATA_DIR / "cache.db"


def resource_path(*parts: str) -> Path:
    """Resolve a bundled resource path, working both in dev and under PyInstaller."""
    if getattr(sys, "frozen", False):  # packaged by PyInstaller
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    return base.joinpath(*parts)


# --------------------------------------------------------------------------- #
# Non-secret settings
# --------------------------------------------------------------------------- #
DEFAULT_SETTINGS: dict[str, Any] = {
    "drive_folder_id": "",
    "drive_folder_name": "",
    "drive_mixes_folder_id": "",     # destination folder for finished mixes
    "drive_mixes_folder_name": "",
    "google_client_id": "",
    "google_client_secret": "",
    "anthropic_model": "claude-opus-4-8",
    "target_bpm_tolerance": 6,       # BPM gap considered "smooth"
    "energy_scale": 10,              # energy reported on a 0..N scale
    "analysis_engine": "librosa",    # "librosa" | "essentia"
    "essentia_genre_model": "",      # optional path to an Essentia genre model
    "crossfade_seconds": 8,          # transition-audition crossfade length
    "stem_model": "htdemucs",        # Demucs model used for stem separation
    "audio_device_id": "",           # selected OS audio output device (index/id)
    "audio_device_name": "",
}


def load_settings() -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            settings.update(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def save_settings(values: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    settings.update({k: v for k, v in values.items() if k in DEFAULT_SETTINGS})
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return settings


# --------------------------------------------------------------------------- #
# Secret storage (Anthropic API key) — encrypted at rest with a local key
# --------------------------------------------------------------------------- #
def _fernet() -> Fernet:
    if KEYFILE_PATH.exists():
        key = KEYFILE_PATH.read_bytes()
    else:
        key = Fernet.generate_key()
        KEYFILE_PATH.write_bytes(key)
        try:  # best-effort tighten permissions (POSIX)
            os.chmod(KEYFILE_PATH, 0o600)
        except OSError:
            pass
    return Fernet(key)


def _load_secrets() -> dict[str, str]:
    if not SECRETS_PATH.exists():
        return {}
    try:
        raw = _fernet().decrypt(SECRETS_PATH.read_bytes())
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _save_secrets(secrets: dict[str, str]) -> None:
    token = _fernet().encrypt(json.dumps(secrets).encode("utf-8"))
    SECRETS_PATH.write_bytes(token)
    try:
        os.chmod(SECRETS_PATH, 0o600)
    except OSError:
        pass


def get_anthropic_key() -> str:
    return _load_secrets().get("anthropic_api_key", "")


def set_anthropic_key(value: str) -> None:
    secrets = _load_secrets()
    secrets["anthropic_api_key"] = value.strip()
    _save_secrets(secrets)


def has_anthropic_key() -> bool:
    return bool(get_anthropic_key())
