"""Distance maths for deciding which incidents sit on a route.

Everything here works on plain (lat, lng) degree pairs. Distances come back in
metres. The corridor test is deliberately simple: we treat the trip as a
straight line from origin to destination and keep incidents within a set
distance of it. That over-reports on a route that bends a long way around
(Osborne Park to Fremantle, say) and it cannot know which freeway you'll
actually pick - but it never silently misses something sitting directly in the
way, which is the failure that matters.
"""
from __future__ import annotations

import math
from typing import Iterable

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in metres between two (lat, lng) points."""
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def _to_local_xy(point: tuple[float, float], origin: tuple[float, float]) -> tuple[float, float]:
    """Project to metres east/north of `origin`.

    Over the tens of kilometres we care about, a flat projection is accurate to
    well under the corridor width, and it keeps the segment maths trivial.
    """
    lat_scale = EARTH_RADIUS_M * math.pi / 180.0
    lng_scale = lat_scale * math.cos(math.radians(origin[0]))
    return ((point[1] - origin[1]) * lng_scale, (point[0] - origin[0]) * lat_scale)


def distance_to_segment_m(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Shortest distance in metres from `point` to the line between start and end."""
    px, py = _to_local_xy(point, start)
    ex, ey = _to_local_xy(end, start)
    seg_len_sq = ex * ex + ey * ey
    if seg_len_sq == 0.0:
        return math.hypot(px, py)
    # How far along the segment the closest point falls, clamped to its ends.
    t = max(0.0, min(1.0, (px * ex + py * ey) / seg_len_sq))
    return math.hypot(px - t * ex, py - t * ey)


def progress_along_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    """Where `point` falls along start->end, as 0.0 at the start and 1.0 at the end.

    Used to order incidents the way the driver will meet them, and to drop ones
    already behind them.
    """
    px, py = _to_local_xy(point, start)
    ex, ey = _to_local_xy(end, start)
    seg_len_sq = ex * ex + ey * ey
    if seg_len_sq == 0.0:
        return 0.0
    return max(0.0, min(1.0, (px * ex + py * ey) / seg_len_sq))


def within_corridor(
    points: Iterable[tuple[float, float]],
    start: tuple[float, float],
    end: tuple[float, float],
    corridor_m: float,
) -> bool:
    """True if any of `points` comes within `corridor_m` of the start->end line.

    Incidents can be reported as a line (a closed stretch of road), so any part
    of it being close enough counts.
    """
    return any(distance_to_segment_m(p, start, end) <= corridor_m for p in points)
