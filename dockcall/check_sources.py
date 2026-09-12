#!/usr/bin/env python3
"""Test whether the Main Roads endpoints in sources.json actually work.

Run this first:

    python check_sources.py

It fetches each configured URL and reports what came back - how many incidents,
and what the field names are. The field names matter: if they don't look like
anything Dock Call recognises, it prints them so they can be added to the lists
in dockcall/mainroads.py.

This exists because the endpoints in sources.json could NOT be verified when
Dock Call was written - the Main Roads hosts were unreachable from that
environment. Treat the URLs in sources.json as a starting guess.
"""
from __future__ import annotations

import asyncio
import json
import sys

import httpx

from dockcall import mainroads


async def check(name: str, url: str) -> bool:
    print(f"\n--- {name} ---")
    if not url.strip():
        print("  not configured (blank in sources.json)")
        return False
    print(f"  {url[:110]}{'...' if len(url) > 110 else ''}")
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.RequestError as exc:
        print(f"  FAILED to connect: {type(exc).__name__}: {exc}")
        return False

    print(f"  HTTP {response.status_code}  ({len(response.content):,} bytes)")
    if response.status_code != 200:
        print(f"  Body starts: {response.text[:200]!r}")
        return False

    try:
        payload = response.json()
    except ValueError:
        print(f"  Not JSON. Body starts: {response.text[:200]!r}")
        return False

    features = payload.get("features")
    if features is None:
        print("  JSON, but no 'features' key - this probably isn't the GeoJSON endpoint.")
        print(f"  Top-level keys: {sorted(payload)[:15]}")
        return False

    print(f"  GeoJSON with {len(features)} features.")
    if not features:
        print("  Empty right now - that can simply mean no incidents. Try again later.")
        return True

    props = features[0].get("properties") or {}
    print(f"  Field names: {sorted(props)}")

    parsed = mainroads.parse_incidents(payload)
    print(f"  Dock Call could place {len(parsed)} of {len(features)} on a map.")
    if parsed:
        first = parsed[0]
        print("  First one, as Dock Call reads it:")
        for key in ("title", "road", "status", "detail", "reported"):
            print(f"    {key:9} {first[key] or '(nothing found)'}")
        unknown = [k for k in props if not any(
            mainroads._normalise(k) == mainroads._normalise(c)
            for group in (mainroads._TITLE_FIELDS, mainroads._DETAIL_FIELDS,
                          mainroads._ROAD_FIELDS, mainroads._STATUS_FIELDS,
                          mainroads._TIME_FIELDS)
            for c in group
        )]
        if unknown and not first["detail"]:
            print(f"\n  Fields Dock Call ignored: {sorted(unknown)}")
            print("  If something useful is in there, add its name to the lists at the")
            print("  top of dockcall/mainroads.py.")
    return True


async def main() -> int:
    sources = mainroads.load_sources()
    if not sources:
        print("sources.json not found or empty.")
        return 1

    ok = await check("Incidents", sources.get("incidents_geojson", ""))
    cameras = sources.get("cameras_geojson", "")
    if cameras.strip():
        await check("Cameras", cameras)
    else:
        print("\n--- Cameras ---\n  not configured yet (waiting on the Main Roads reply)")

    print("\n" + ("Incidents are working. Start the app with: python run.py"
                  if ok else
                  "Incidents are NOT working. Fix the URL in sources.json, or run the app\n"
                  "with 'python run.py --demo' to look at it with invented data."))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
