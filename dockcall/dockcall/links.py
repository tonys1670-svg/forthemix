"""Hand-off links to the apps that already do navigation well.

Dock Call does not do turn-by-turn. It works out what's in the way, then hands
the driver to whichever app they prefer. These are all public URL schemes - no
API keys, no terms to agree to, nothing fetched.

Waze is hand-off only by necessity: it publishes no way to read its traffic
data (its data-sharing programme is for government agencies), so the only
legitimate way to use Waze is to send the driver into the Waze app.
"""
from __future__ import annotations

from urllib.parse import quote


def google_maps_directions(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> str:
    """Google Maps directions, traffic-aware, opens in the app if installed."""
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={origin[0]:.6f},{origin[1]:.6f}"
        f"&destination={destination[0]:.6f},{destination[1]:.6f}"
        "&travelmode=driving"
    )


def waze_navigate(destination: tuple[float, float]) -> str:
    """Waze navigation to a point. Waze picks its own route from where you are."""
    return f"https://waze.com/ul?ll={destination[0]:.6f}%2C{destination[1]:.6f}&navigate=yes"


def mainroads_travel_map() -> str:
    """The Main Roads WA Travel Map - the official live traffic and camera view."""
    return "https://travelmap.mainroads.wa.gov.au/"


def all_links(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> dict[str, str]:
    return {
        "google_maps": google_maps_directions(origin, destination),
        "waze": waze_navigate(destination),
        "travel_map": mainroads_travel_map(),
    }
