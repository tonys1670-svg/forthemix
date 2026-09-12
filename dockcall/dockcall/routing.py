"""Optional traffic-aware drive time from the Google Maps Routes API.

This is the only part of Dock Call that needs a paid API key, and the only part
that costs money to run. Without a key the app still works - it reports the
straight-line distance instead of a drive time, and the Google Maps hand-off
button gives the driver a real ETA in one tap.

Set the key in the environment before starting:

    export GOOGLE_MAPS_API_KEY=...        # macOS / Linux
    set GOOGLE_MAPS_API_KEY=...           # Windows

NOTE: this call could not be tested from the environment it was written in
(no outbound access to Google). The first run with a real key is the test.
Failures are reported, never silently swallowed.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"


def has_key() -> bool:
    return bool(os.environ.get("GOOGLE_MAPS_API_KEY", "").strip())


def _waypoint(point: tuple[float, float]) -> dict[str, Any]:
    return {"location": {"latLng": {"latitude": point[0], "longitude": point[1]}}}


async def drive_time(
    origin: tuple[float, float],
    destination: tuple[float, float],
    timeout: float = 15.0,
) -> tuple[dict[str, Any] | None, str]:
    """Traffic-aware drive time. Returns (result, status).

    `result` carries seconds, metres, and the route's summary description.
    `status` is "ok", "no_key", or a short reason it failed.
    """
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        return None, "no_key"

    body = {
        "origin": _waypoint(origin),
        "destination": _waypoint(destination),
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
    }
    headers = {
        "X-Goog-Api-Key": key,
        # Routes requires an explicit field mask; asking for everything is rejected.
        "X-Goog-FieldMask": "routes.duration,routes.distanceMeters,routes.description",
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(ROUTES_URL, json=body, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("error", {}).get("message", "")
        except ValueError:
            pass
        return None, f"Google Routes returned HTTP {exc.response.status_code}. {detail}".strip()
    except httpx.RequestError as exc:
        return None, f"could not reach Google Routes ({type(exc).__name__})"
    except ValueError:
        return None, "Google Routes did not return JSON"

    routes = payload.get("routes") or []
    if not routes:
        return None, "Google Routes found no route between those points"

    route = routes[0]
    # Duration comes back as a protobuf duration string, e.g. "1284s".
    raw_duration = str(route.get("duration", "0s"))
    try:
        seconds = int(float(raw_duration.rstrip("s")))
    except ValueError:
        seconds = 0

    return (
        {
            "seconds": seconds,
            "minutes": round(seconds / 60),
            "metres": int(route.get("distanceMeters") or 0),
            "description": route.get("description") or "",
        },
        "ok",
    )
