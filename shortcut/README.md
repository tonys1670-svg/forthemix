# Short Cut — beta

Tells a driver what's in the way between where they are and where they're going.

You open it on your phone, it finds you, you tap or say a destination, and it
answers: any Main Roads incidents on that run, how long it takes, and a button
to drive it in Google Maps, Waze, or the Main Roads Travel Map.

**This is a beta.** Some of it is proven, some of it isn't, and the table further
down says honestly which is which.

---

## Run it

You need Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python check_sources.py            # does the Main Roads data actually work?
python run.py                      # start it
```

`run.py` prints two addresses — one for this computer, one for your phone.

**If `check_sources.py` fails**, the Main Roads URL needs fixing (see *The one
thing that needs fixing* below). In the meantime you can still look at the whole
app with invented data:

```bash
python run.py --demo
```

Demo mode puts a warning banner at the top of every screen, and the incidents
it shows are made up. It exists so you can judge the app, not the roads.

---

## Getting location to work on your phone

**This will bite you, so read it first.** Phones only share location with pages
served over **https**, or over plain http when the address is `localhost`. So
typing `http://192.168.x.x:8750` into your phone gets you the app, but the
location will be refused and nothing will work.

Two ways around it:

**Easiest — a temporary https address.** Install
[cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/),
then with Short Cut already running:

```bash
cloudflared tunnel --url http://localhost:8750
```

It prints an `https://something.trycloudflare.com` address. Open that on your
phone and location works. The address dies when you close it, which is fine for
testing — and worth knowing that while it's open, anyone with that link can
reach your app.

**Or test on the computer first.** Open `http://127.0.0.1:8750` in a normal
browser. Location works there because it's localhost. You won't get the
phone-sized layout, but everything else is real.

Once you've decided the app is worth keeping, it gets hosted properly with a
real https address and this whole problem goes away.

---

## What's actually proven, and what isn't

| Part | State | Notes |
| --- | --- | --- |
| The page, the flow, the layout | **Tested, works** | Runs, responds, handles bad input |
| Finding you (GPS) | **Built, not tested on a phone** | Standard browser feature. Needs https — see above |
| Deciding which incidents are on your route | **Tested, works** | Correctly flags a Mitchell Fwy incident for a CBD run and correctly ignores it for a Fremantle run |
| Speaking the answer out loud | **Built, not tested on a phone** | Built into the phone, costs nothing |
| Saying the destination out loud | **Built, expect trouble on iPhone** | The known weak spot. Falls back to tapping, with a message saying why |
| Google Maps / Waze / Travel Map buttons | **Built, not tested on a phone** | Public link formats, no keys, nothing fetched |
| Reading live Main Roads incidents | **NOT WORKING — needs a URL** | See below |
| Drive times from Google | **Built, never run** | Needs a paid key. Untested because this had no Google access either |
| Camera images | **Not built** | Waiting on the Main Roads reply |

---

## The one thing that needs fixing

`sources.json` holds the Main Roads incident URL, and **that URL is a guess.**
Every Main Roads host was unreachable from the environment Short Cut was built
in, so the real endpoint could not be looked up, let alone tested.

To fix it:

1. Go to the Main Roads open data portal and find **WebEOC Road Incidents**.
2. Copy its GeoJSON or FeatureServer query URL.
3. Paste it into `sources.json` as `incidents_geojson`.
4. Run `python check_sources.py`.

`check_sources.py` prints what came back, including the field names. If the
field names aren't ones Short Cut recognises, it says so and tells you where to
add them — the lists at the top of `shortcut/mainroads.py`.

**Until that URL works, Short Cut says "not checked" rather than "clear".** That
distinction is deliberate: an app that reports empty roads because it couldn't
reach its data is worse than no app at all.

---

## About the three sources you asked for

**Main Roads WA** — the one real data source. Free, open, Creative Commons
Attribution. Incidents now; cameras once they reply about access.

**Google Maps** — two separate things. The **button** that opens Google Maps
with your route is free and needs nothing. The **drive time shown inside Dock
Call** needs a paid API key:

```bash
export GOOGLE_MAPS_API_KEY=your-key-here    # Windows: set GOOGLE_MAPS_API_KEY=...
python run.py
```

Without a key everything still works — you get straight-line distance instead of
a drive time, and one tap on the Google Maps button gives you a real ETA anyway.

**Waze** — hand-off only, and that isn't a shortcut. Waze publishes no way to
read its traffic data; its data-sharing programme is for government agencies,
and scraping it breaks their terms. So the only legitimate way to use Waze is
the button that sends you into the Waze app, which is what's here. Waze is
owned by Google, so much of the same underlying traffic data reaches you through
the Google side anyway.

---

## Deliberately not doing

- **Turn-by-turn navigation.** Short Cut says what's in the way and which run to
  take. Google and Waze do the driving directions, and they do them better.
- **Anything while the vehicle is moving.** Built for use parked. Phone in hand
  while driving is illegal in WA.
- **Background tracking.** Close it or lock the phone and it stops. It cannot
  follow anyone around.

---

## What's in here

```
run.py                    start it
check_sources.py          test whether the Main Roads data works
places.json               your saved destinations - edit this
sources.json              Main Roads URLs - needs the real incident URL
shortcut/
  server.py               the web endpoints
  mainroads.py            reading and parsing incident data
  geo.py                  working out what's on your route
  routing.py              optional Google drive times
  links.py                the Google Maps / Waze / Travel Map buttons
  demo.py                 invented incidents for --demo
  static/index.html       the whole phone app
```

`places.json` is the file you'll actually want to edit — add the venues you go
to. The coordinates in there now are **approximate**: close enough to decide
whether an incident is on the route, but check them before trusting them.

## Where the background is

`docs/` carries the thinking behind the app, kept as it was written:

- `idea-notes.md` — the whole discussion: what it's for, what was cut and why,
  the data sources, costs, and the risks still outstanding.
- `mainroads-data-enquiry-email.md` — the enquiry sent to Main Roads WA on
  11 Sep 2026 about camera access and licensing. The reply decides whether
  camera reading is possible at all.
- `mockup.html` — the clickable design mock-up this app was built from. Open it
  in a browser. All invented data.
