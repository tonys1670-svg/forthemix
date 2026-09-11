# Voice Traffic Assistant — idea notes

**Status:** early discussion, nothing built
**Started:** 2026-09-11
**Owner:** Tony

---

## The idea in one line

Talk to an app — "what's the traffic like getting to [place] right now?" — and get a
spoken, plain-English answer that pulls from multiple traffic sources at once,
including live traffic cameras.

## The core behaviour

1. I say where I'm going (voice, not typing).
2. The app works out the likely route(s).
3. It checks several sources: routing/ETA services, official incident feeds,
   and the live traffic cameras along that route.
4. It answers me conversationally — not a map, a sentence. "35 minutes, about
   10 worse than usual. There's a breakdown on the M4 near Silverwater — the
   camera shows two lanes blocked. If you leave in 20 it should have cleared."

## What makes it different from just using Google Maps

This is the question the whole idea lives or dies on, because Google Maps
already does voice input and traffic-aware ETAs for free.

Candidate answers (to be decided — see Open questions):

- **Synthesis.** Google gives you a number. It does not tell you *why* it's slow,
  or what the incident actually is. Combining the official incident feed with
  the ETA gives you the reason, not just the delay.
- **Eyes on the road.** Nobody offers "look at the actual camera and tell me what
  you see." A vision model reading traffic-camera stills along the route is the
  genuinely novel piece — and no big provider does it.
- **Judgement, not data.** "Should I leave now or wait?" / "Is the M4 or Parramatta
  Road better right now?" are questions Maps can't answer in words.

## Data sources — reality check

| Source | Available? | Notes |
| --- | --- | --- |
| Official state traffic feed (e.g. Live Traffic NSW) | **Likely yes, free** | Government open-data. Incidents, hazards, roadworks, and camera images. Needs verifying per state. |
| Traffic cameras | **Likely yes, free** | Usually published as stills that refresh every minute or so, via the same government feed. This is the interesting one. |
| Google Maps | **Yes, paid** | Routes API gives traffic-aware ETAs. Has a free monthly allowance, costs money past it. |
| Commercial traffic APIs (TomTom, HERE) | **Yes, free tier** | Incidents + traffic flow. Alternative to Google. |
| Waze | **No** | No public API for reading traffic. Its data-share programme is for government agencies only. Scraping it breaks their terms. **Waze is off the table.** |
| Police / agency social media posts | **Maybe** | Often the same info as the official feed, arriving earlier. Access depends on the platform's API pricing. |

## Open questions

- [ ] Which city/state? This decides which official feeds exist and how good they are.
- [ ] What's it running on — phone app, web page, or a voice device in the car?
- [ ] Personal tool, or something for OMG Events (crew and trucks getting to venues)?
- [ ] Ask-on-demand only, or does it warn you unprompted before a trip?
- [ ] Just me, or other people using it too? (Changes everything about cost and build.)

## Decisions made

_(nothing yet)_

## Rejected

- **Waze as a data source** — no legitimate public access.
