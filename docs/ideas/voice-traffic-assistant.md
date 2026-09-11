# Voice Traffic Assistant — idea notes

**Status:** early discussion, nothing built
**Started:** 2026-09-11
**Owner:** Tony
**Location:** Perth, Western Australia
**Platform:** phone (iOS + Android)
**First users:** OMG Events staff, crew and subcontractors

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

## The real job: getting crew and trucks to bump-in on time

Because the first users are OMG Events people, the question the app answers is
not really "what's the traffic like". It's **"will my crew make the loading dock
window, and if not, what do I do about it?"**

That reframing matters because:

- **Events have hard deadlines.** A venue dock slot at 6am is not a suggestion.
  Missing it can mean fines, a lost slot, or a late show.
- **Trucks are not cars.** Height limits, weight limits, restricted routes. A
  car ETA from Google is the wrong answer for a 12-tonne truck. Nobody serves
  this well.
- **One destination, many people.** The production manager wants one view of
  everyone converging on the venue — not each person asking separately.
- **Warning beats asking.** The highest-value moment isn't someone asking at
  5am. It's the app telling the production manager at 4:30am: "the Mandurah
  crew needs to leave 25 minutes earlier today."

## Data sources — reality check (Perth / WA)

| Source | Available? | Notes |
| --- | --- | --- |
| **Main Roads WA open data** | **Yes, free** | Confirmed. Runs an open data portal under a Creative Commons Attribution licence. The "WebEOC Road Incidents" dataset is what feeds their own Travel Map — road closures and incident types — available as a REST API, GeoJSON, CSV and KML. Developer contact: gis@mainroads.wa.gov.au |
| **Main Roads WA traffic cameras** | **Yes — details to confirm** | A traffic cameras dataset exists on the same portal. Third-party aggregators claim 600+ cameras across Perth, covering Mitchell, Kwinana and Graham Farmer Freeways, Tonkin and Roe Highways, Joondalup to Mandurah. **Not yet confirmed: whether the dataset gives us image URLs, how often they refresh, and whether the licence covers commercial use.** This is the single most important thing to verify. |
| Google Maps | **Yes, paid** | Routes API gives traffic-aware ETAs. Has a free monthly allowance, costs money past it. |
| Commercial traffic APIs (TomTom, HERE) | **Yes, free tier** | Incidents + traffic flow. Alternative to Google. |
| Waze | **No** | No public API for reading traffic. Its data-share programme is for government agencies only. Scraping it breaks their terms. **Waze is off the table.** |
| Police / agency social media posts | **Maybe** | Often the same info as the official feed, arriving earlier. Access depends on the platform's API pricing. |

## Decided shape: a mobile web app (PWA)

The driver is the primary user, and a typical day is a **run of several stops**,
not one destination. That points at a web app saved to the phone's home screen:

- One codebase, works on iPhone and Android.
- No app store, no review process, no developer accounts.
- Subcontractors install nothing — you send a link, they tap "Add to Home Screen".
- Updates are instant. Fix something and everyone has it next time they open it.

### What a phone web app can do

- Look and open like a real app (own icon, full screen, no browser bars).
- Listen to speech and speak the answer back out loud.
- Read GPS location while it's open, so "from where I am now" works.
- Show live camera images.
- Hold the day's run of stops and track progress through them.

### What it genuinely cannot do

These are platform limits, not effort problems — worth knowing before planning
around them:

- **No background tracking.** Once the phone is locked or the app is closed, it
  stops. It cannot quietly follow the driver around. iPhones are strict here.
- **No wake word.** There's no "hey app" while driving. Someone has to tap.
- **Notifications are second-class.** Android is fine. On iPhone, push only works
  if the user has added it to their home screen, and it's less dependable than
  a native app.

### The consequence, and the safety line

Because it needs a tap, this cannot be a thing drivers poke at while moving —
and in WA that's illegal anyway. So design it for **the stop, not the motion**:

> Driver finishes a drop, still parked. One tap: "what's the run to the next
> one?" App speaks the answer. Driver puts the phone down and goes.

That fits a multi-stop day better than a single-destination app would, and it
keeps hands off the phone in traffic.

### Biggest technical unknown

Voice input on iPhone. Safari's built-in speech recognition is inconsistent, so
the fallback is: record a short clip and send it to a speech-to-text service.
More reliable and behaves the same on both platforms. **This needs testing on a
real iPhone early** — it's the riskiest assumption in the plan.

## Superseded: the build-shape question

A native app on both iOS and Android is the heaviest possible path: two
codebases (or one cross-platform one), two developer accounts, app store
review, and every subcontractor has to agree to install something. That last
part is the real risk — you don't control a subcontractor's phone.

Lighter options that may deliver most of the value:

- **A web page, saved to the home screen.** Looks and behaves like an app, works
  on both platforms, no app store, no install friction. Can do voice input.
- **Push it out by message instead.** The crew installs nothing. They get an SMS
  or WhatsApp: "Heads up — crash on Tonkin, leave 20 min earlier for the
  Crown bump-in." Only the production manager needs a real interface.
- **Full native app.** Best experience, hands-free in the car, but the biggest
  build and the hardest adoption.

## Open questions

- [ ] Confirm the Main Roads camera dataset gives usable image URLs, refresh rate, and a licence that allows commercial use.
- [x] ~~Driver or production manager?~~ **Driver.** They run multiple stops a day.
- [ ] Does it need to handle trucks differently from cars, or is everyone in vans and utes?
- [ ] Reactive (I ask) or proactive (it warns me)? Proactive needs to know the run sheet.
- [ ] How does it learn where people are going — manual entry, or pulled from an existing run sheet / job system?
- [ ] Roughly how many people would use it, and how often?

## Decisions made

- **Perth, WA** — Main Roads WA is the primary data source.
- **Mobile web app (PWA)**, not a native app — one build, no app store, no install friction for subcontractors.
- **Primary user is the driver**, working a run of several stops per day.
- **Designed for use while stopped**, never while moving.
- **OMG Events crew first**, not a public product, at least initially.

## Rejected

- **Waze as a data source** — no legitimate public access.

## Housekeeping

These notes currently live in the ForTheMix repo because that's where this
conversation started. This is an unrelated project and should get its own
repository before any code is written.
