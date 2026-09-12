"""Invented incidents, so the app can be looked at before the data source is confirmed.

Run with DOCKCALL_DEMO=1 to use these instead of live Main Roads data. Every
response is flagged `demo: true` and the page says so on screen - nothing here
should ever be mistaken for a real road condition.
"""
from __future__ import annotations

from typing import Any

# Placed on real Perth roads so the corridor filter has something honest to do.
DEMO_INCIDENTS: list[dict[str, Any]] = [
    {
        "title": "Crash",
        "detail": "Two vehicles, right lane blocked. Tow truck en route.",
        "road": "Mitchell Fwy southbound near Vincent St",
        "status": "Lane closed",
        "reported": "05:51",
        "points": [(-31.9340, 115.8395)],
        "lat": -31.9340,
        "lng": 115.8395,
    },
    {
        "title": "Roadworks",
        "detail": "Resurfacing, reduced to one lane overnight until 5am.",
        "road": "Graham Farmer Fwy eastbound",
        "status": "Lane closed",
        "reported": "22:00 yesterday",
        "points": [(-31.9430, 115.8720)],
        "lat": -31.9430,
        "lng": 115.8720,
    },
    {
        "title": "Flooding",
        "detail": "Water over the road after heavy rain. Drive to conditions.",
        "road": "Great Eastern Hwy near Belmont",
        "status": "Hazard",
        "reported": "06:10",
        "points": [(-31.9460, 115.9300)],
        "lat": -31.9460,
        "lng": 115.9300,
    },
    {
        "title": "Breakdown",
        "detail": "Truck on the shoulder, traffic passing slowly.",
        "road": "Kwinana Fwy northbound at Canning Hwy",
        "status": "Hazard",
        "reported": "06:18",
        "points": [(-31.9940, 115.8580)],
        "lat": -31.9940,
        "lng": 115.8580,
    },
]
