"""Enumerate and select an OS audio output device (optional: sounddevice).

pywebview's browser layer can't pick an OS output device, so this is done
Python-side. Enumeration works wherever ``sounddevice`` is installed; actually
routing playback through the chosen device is not wired yet (playback is
currently browser-side), which the responses make explicit via ``wired``.
"""
from __future__ import annotations


def is_available() -> bool:
    try:
        import sounddevice  # noqa: F401
        return True
    except Exception:
        return False


def list_output_devices() -> dict:
    if not is_available():
        return {
            "devices": [],
            "wired": False,
            "note": "sounddevice not installed — run 'pip install sounddevice' to enable OS output device selection.",
        }
    import sounddevice as sd

    try:
        default_out = sd.default.device[1] if sd.default.device is not None else None
    except Exception:
        default_out = None

    devices = []
    try:
        for idx, d in enumerate(sd.query_devices()):
            if d.get("max_output_channels", 0) > 0:
                devices.append({
                    "id": str(idx),
                    "name": d.get("name", f"Device {idx}"),
                    "default": idx == default_out,
                })
    except Exception as exc:
        return {"devices": [], "wired": False, "note": f"Could not enumerate devices: {exc}"}

    return {
        "devices": devices,
        "wired": False,
        "note": "Devices enumerated and the selection is saved, but playback is not yet routed "
                "through Python to this device (playback is currently browser-side). See README.",
    }
