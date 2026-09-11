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

## Working name: Dock Call

"Bump-in" and "call time" are the words the crew already uses. The app's job is
to answer one question — *will I make the dock call?* — so it takes that name.

## Artefacts so far

- **Clickable mock-up:** `docs/ideas/dock-call-mockup.html`
  (published at https://claude.ai/code/artifact/0232477e-4774-431e-a040-4e2a6c3bebb7).
  All invented data. Shows the home screen with the day's run, the listening
  state, and the spoken answer with camera panel.
- **Data enquiry email:** `docs/ideas/mainroads-data-enquiry-email.md` — draft to
  Main Roads WA, not yet sent.

## What the mock-up establishes

- The home screen is **the day's run**, not a search box. The driver already
  knows where they're going.
- The answer leads with **one word** — Clear / Tight / Late — then the detail.
- The headline number is **spare time against the dock booking**, not drive time.
  That's the number Google can't give you because it doesn't know the booking.
- The camera is **described in words as well as shown**. A driver glancing at a
  phone shouldn't have to interpret a picture.
- Traffic-light colours throughout. No one needs to be taught them.
- Screen is always dark — it's used at 4:30am in a cab.

## Open questions

- [ ] **Send the Main Roads email** and confirm camera image URLs, refresh rate, and commercial licence. Everything else waits on this.
- [ ] How does the day's run get into the app — typed in each morning, or pulled from an existing job sheet?
- [ ] Where do dock booking times live today? The app is much weaker without them.
- [ ] Do the trucks need different routing from the vans?
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

---

# Build plan and running costs

Written 2026-09-11. Assumes the Main Roads answer comes back positive; if the
cameras are closed off, Stage 3 disappears and the rest still stands.

## The four pieces

The app is smaller than it sounds. It's four things joined together:

1. **A run list** — the day's stops and their dock times. Held per driver.
2. **A route and an ETA** — from a routing service, traffic-aware.
3. **A picture of what's wrong** — Main Roads incidents, plus the cameras that
   sit along the route.
4. **A judgement** — an AI model turns all of the above into one spoken sentence
   and a verdict.

Only the fourth is novel. The first three are plumbing.

## The one genuinely fiddly problem

**Which cameras are on my route?**

The routing service returns the route as a line on a map. The camera dataset
gives each camera a location. So: keep the cameras within a few hundred metres
of that line, and ahead of the driver rather than behind. That's ordinary
geometry, not research — but it's the bit that has to be got right, because
sending the wrong camera to the AI produces a confident, wrong answer.

## Build it in stages, value first and risk last

Each stage is useful on its own. Stop at any point and you still have something.

### Stage 1 — the run sheet that watches itself
No voice. No AI. A web page showing today's stops, checking the Main Roads
incident feed, and flagging anything on the roads you're about to use.

Gives you: "there's something happening on your route" — which is most of the
value, for a fraction of the work.

### Stage 2 — the verdict
Add routing and dock times. Now it says **Clear / Tight / Late** with minutes of
spare time against the booking.

This is the stage where it becomes a product rather than a feed reader. It's the
number Google structurally cannot give you, because Google doesn't know about
the 07:00 slot at Dock 3.

### Stage 3 — eyes on the cameras
Add the AI. It reads the camera stills and writes the plain-English answer.

This is the differentiator, and it's also the stage that depends on the Main
Roads answer.

### Stage 4 — voice
Speaking the answer out loud is easy and free — phones already do it. Speaking
*to* it is the hard half, and it's genuinely optional: a tap plus a couple of
preset questions covers most of what a driver needs.

Left until last deliberately. It's the least essential and the most likely to
misbehave on iPhones.

## What it costs to run

### The AI — the part that can be priced properly

Each question means sending the model a couple of camera images plus the
incident and route details, and getting back a short spoken answer.

At Claude Opus 5 rates (US$5 per million tokens in, US$25 out), that works out
at roughly **2 to 6 US cents per question**, depending on how many cameras are
involved.

Say six drivers, five stops each, one question per stop, 22 working days —
around 660 questions a month:

| Volume | Rough monthly cost (USD) |
| --- | --- |
| 660 questions | **$15 – $45** |
| Double that | $30 – $90 |

Cheaper models exist at roughly a third the cost, and that's a decision worth
revisiting once it's running and the quality is visible — but it's a real
decision, not a free saving.

### Everything else — needs checking, don't assume

| Item | Cost | Confidence |
| --- | --- | --- |
| Main Roads data | Free | Confirmed — open data, CC licence |
| Speaking the answer out loud | Free | The phone does it; no service needed |
| Hosting the web app | Small — plausibly free at this scale | Reasonably confident |
| Routing / ETA service | **Unknown** | Google and TomTom both have free allowances then per-request pricing. Needs pricing properly. |
| Speech-to-text (Stage 4 only) | **Unknown** | Priced per second of audio. Clips are a few seconds, so likely small — but unpriced. |

**Don't let the precise AI figure create false confidence.** The two unknowns
above could each exceed it. They need a proper look before anyone commits.

## The honest risk list

- **The cameras might be closed off.** Everything distinctive rests on this.
  The email goes first for a reason.
- **Bad camera picks produce confident nonsense.** An AI handed the wrong camera
  will describe it fluently and be completely wrong. This needs testing against
  reality, not just checking that it runs.
- **Dock times may not exist in any system.** If they live in people's heads and
  WhatsApp threads, Stage 2 has nothing to work from, and the app drops back to
  being a nicer traffic page.
- **Adoption.** Subcontractors have to actually open it. A web link is the
  lowest-friction option available, but it isn't zero.

## Still open

- Where do dock booking times live today?
- How does a driver's run get into the app each morning?

---

# Scope cut — 11 Sep 2026

Tony's call: **keep it simple.** The app is now one thing.

> Geolocate me. I say or type my destination. Tell me any issues and which
> route to take.

## What's in

1. The phone reports where you are — no typing.
2. You say (or tap) where you're going.
3. It checks Main Roads incidents against your likely routes.
4. It reads the cameras along the way and describes them.
5. It speaks the answer and shows it on screen.

Saved places carry most of the input: crew go to the same dozen venues, so the
common case is one tap, not an address typed one-handed at 6am.

## What's out, and what that costs

Dropped: the day's run sheet, dock booking times, multi-stop tracking, and the
production-manager view.

**The cost of dropping dock times** is the sharpest answer to "why not just use
Google Maps". The app can no longer say *"you'll miss your 07:00 slot by six
minutes"* — only *"34 minutes, and here's what's wrong."*

What still can't be got anywhere else:

- **A camera actually read and described**, rather than a coloured line on a map.
- **Plain English on what's blocking you**, not just a slower number.
- **An answer you can listen to** instead of reading while parked.

Narrower, but real — and it removes the dependency that was most likely to
sink the whole thing, since nobody yet knows where dock times live.

## Also out of scope, deliberately

- **Turn-by-turn navigation.** It names the run to take; the driver drives it
  however they normally would. Not competing with anyone's nav app.
- **Anything while the vehicle is moving.**

## Effect on the build stages

The earlier four-stage plan collapses to three, and Stage 2's hardest
dependency disappears:

1. **Where am I → where am I going → what's on that road.** Location, saved
   places, Main Roads incident feed. No AI yet.
2. **Add the route and the drive time**, so it can say which run to take and
   how long.
3. **Add the AI** — camera reads and the spoken answer. Still gated on the
   Main Roads reply.

Voice input folds into Stage 3 rather than being its own stage, because typing
into a saved-places list is a perfectly good fallback if iPhone voice misbehaves.

## Still open

- Nothing blocking. The Main Roads email is the only thing standing between
  this and a real Stage 1.
