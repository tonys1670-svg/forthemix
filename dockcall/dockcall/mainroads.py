"""Reading live incidents from Main Roads Western Australia open data.

The endpoint URL lives in sources.json because it could not be verified when
this was written - the Main Roads hosts were unreachable from that environment.
So the parser here is deliberately forgiving: it accepts GeoJSON, pulls
coordinates out of whichever geometry type it finds, and looks for the
description fields under any of several plausible names. If Main Roads' field
names differ from the guesses, incidents still come through with coordinates
and whatever text was found, rather than the whole thing failing.

Run `python check_sources.py` to see what the endpoint actually returns.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

# Field names we'll accept for each piece of information, best guess first.
# Matching is case-insensitive and ignores underscores.
_TITLE_FIELDS = ("eventtype", "incidenttype", "type", "event", "category", "title", "name")
_DETAIL_FIELDS = ("description", "comments", "details", "information", "text", "advice")
_ROAD_FIELDS = ("roadname", "road", "street", "location", "locality", "suburb")
_STATUS_FIELDS = ("closuretype", "status", "impact", "severity", "condition")
_TIME_FIELDS = ("starttime", "startdate", "created", "reported", "lastupdated", "updated")

SOURCES_PATH = Path(__file__).resolve().parent.parent / "sources.json"


def load_sources() -> dict[str, Any]:
    """Read sources.json. Missing file is not fatal - we just have no sources."""
    try:
        return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"sources.json is not valid JSON: {exc}") from exc


def _normalise(key: str) -> str:
    return key.lower().replace("_", "").replace(" ", "")


def _pick(props: dict[str, Any], candidates: tuple[str, ...]) -> str:
    """Return the first non-empty property matching any candidate name."""
    lookup = {_normalise(k): v for k, v in props.items()}
    for name in candidates:
        value = lookup.get(_normalise(name))
        if value not in (None, "", "null"):
            return str(value).strip()
    return ""


def _coords_from_geometry(geometry: dict[str, Any] | None) -> list[tuple[float, float]]:
    """Flatten any GeoJSON geometry to a list of (lat, lng) pairs.

    GeoJSON orders coordinates lng-then-lat, which is the reverse of how we use
    them everywhere else, so they're swapped here once.
    """
    if not geometry:
        return []

    points: list[tuple[float, float]] = []

    def walk(node: Any) -> None:
        if (
            isinstance(node, (list, tuple))
            and len(node) >= 2
            and all(isinstance(v, (int, float)) for v in node[:2])
        ):
            lng, lat = float(node[0]), float(node[1])
            # Guard against a source that publishes lat/lng the other way round.
            if -90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0:
                points.append((lat, lng))
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                walk(child)

    walk(geometry.get("coordinates"))
    return points


def parse_incidents(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn a GeoJSON FeatureCollection into our own incident dicts."""
    incidents: list[dict[str, Any]] = []
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        points = _coords_from_geometry(feature.get("geometry"))
        if not points:
            continue  # nothing we can place on a route
        incidents.append(
            {
                "title": _pick(props, _TITLE_FIELDS) or "Road incident",
                "detail": _pick(props, _DETAIL_FIELDS),
                "road": _pick(props, _ROAD_FIELDS),
                "status": _pick(props, _STATUS_FIELDS),
                "reported": _pick(props, _TIME_FIELDS),
                "points": points,
                "lat": points[0][0],
                "lng": points[0][1],
            }
        )
    return incidents


async def fetch_incidents(timeout: float = 15.0) -> tuple[list[dict[str, Any]], str]:
    """Fetch and parse current incidents.

    Returns (incidents, status) where status is "ok", "not_configured", or a
    short human-readable reason it failed. The caller shows the reason to the
    driver rather than pretending the roads are clear.
    """
    sources = load_sources()
    url = (sources.get("incidents_geojson") or "").strip()
    if not url:
        return [], "not_configured"

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        return [], f"source returned HTTP {exc.response.status_code}"
    except httpx.RequestError as exc:
        return [], f"could not reach the data source ({type(exc).__name__})"
    except ValueError:
        return [], "data source did not return JSON"

    if "features" not in payload:
        return [], "data source returned JSON, but not in the expected GeoJSON shape"

    return parse_incidents(payload), "ok"
