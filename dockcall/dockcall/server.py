"""FastAPI application: serves the Dock Call page and answers route questions."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import VERSION, geo, links, mainroads, routing
from .demo import DEMO_INCIDENTS

STATIC_DIR = Path(__file__).resolve().parent / "static"
PLACES_PATH = Path(__file__).resolve().parent.parent / "places.json"

# How far off the straight line between here and there an incident can be and
# still count as "in the way". Perth's freeway network is coarse enough that
# 1.5 km catches the road you're on without dragging in the next suburb.
CORRIDOR_M = 1500.0

app = FastAPI(title="Dock Call", version=VERSION)


def _demo_mode() -> bool:
    return os.environ.get("DOCKCALL_DEMO", "").strip().lower() in ("1", "true", "yes")


def _load_places() -> list[dict[str, Any]]:
    try:
        data = json.loads(PLACES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"places.json is not valid JSON: {exc}") from exc
    return data.get("places", [])


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# --------------------------------------------------------------------------- #
# Status & places
# --------------------------------------------------------------------------- #
@app.get("/api/health")
async def health() -> dict:
    """What's working, so the page can tell the driver the truth about its data."""
    if _demo_mode():
        source_status = "demo"
    else:
        _, source_status = await mainroads.fetch_incidents()
    return {
        "version": VERSION,
        "demo": _demo_mode(),
        "incident_source": source_status,
        "has_google_key": routing.has_key(),
        "attribution": mainroads.load_sources().get("attribution", ""),
    }


@app.get("/api/places")
def places() -> dict:
    return {"places": _load_places()}


# --------------------------------------------------------------------------- #
# The one question the app answers
# --------------------------------------------------------------------------- #
class CheckRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90, description="Driver's current latitude")
    lng: float = Field(..., ge=-180, le=180, description="Driver's current longitude")
    place: str = Field(..., min_length=1, description="Name of a saved place in places.json")


@app.post("/api/check")
async def check(req: CheckRequest) -> dict:
    """Given where the driver is and where they're going, say what's in the way."""
    place = next(
        (p for p in _load_places() if p["name"].lower() == req.place.strip().lower()),
        None,
    )
    if place is None:
        raise HTTPException(404, f"No saved place called {req.place!r}. Check places.json.")

    origin = (req.lat, req.lng)
    destination = (float(place["lat"]), float(place["lng"]))

    if _demo_mode():
        all_incidents, source_status = list(DEMO_INCIDENTS), "demo"
    else:
        all_incidents, source_status = await mainroads.fetch_incidents()

    # Keep only what sits on the way, ordered as the driver will meet it.
    on_route: list[dict[str, Any]] = []
    for incident in all_incidents:
        points = [tuple(p) for p in incident["points"]]
        if not geo.within_corridor(points, origin, destination, CORRIDOR_M):
            continue
        nearest = min(geo.distance_to_segment_m(p, origin, destination) for p in points)
        entry = dict(incident)
        entry.pop("points", None)
        entry["metres_off_route"] = round(nearest)
        entry["progress"] = round(
            geo.progress_along_segment(points[0], origin, destination), 3
        )
        on_route.append(entry)
    on_route.sort(key=lambda i: i["progress"])

    drive, drive_status = await routing.drive_time(origin, destination)

    return {
        "demo": _demo_mode(),
        "destination": {"name": place["name"], "detail": place.get("detail", "")},
        "straight_line_km": round(geo.haversine_m(origin, destination) / 1000.0, 1),
        "drive": drive,
        "drive_status": drive_status,
        "incident_source": source_status,
        "incidents_checked": len(all_incidents),
        "incidents": on_route,
        "links": links.all_links(origin, destination),
        "attribution": mainroads.load_sources().get("attribution", ""),
    }
