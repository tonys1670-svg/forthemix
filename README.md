# 🎧 ForTheMix

Analyse the tracks in a Google Drive folder, build DJ mixes with live
transition feedback, and let Claude curate a set from a plain-English brief —
a private, offline-first alternative to Spotify's AI DJ that works over **your**
music library.

---

## What it does

| Module | What you get |
| --- | --- |
| **Library / Analysis** | Point it at a Google Drive folder. Every track is analysed for **genre, key (Camelot), BPM, and energy**, with a waveform for the player. Results are cached so a folder is only analysed once. |
| **Mix Builder** | Drag tracks into an ordered set. Between every pair, a **transition comments** card scores the blend (harmonic + tempo + energy) and explains *why* it does or doesn't work. Built-in **audio player** can *audition* a transition — it rolls the tail of one track into the start of the next. |
| **AI Curator** | Describe the vibe ("sunset rooftop, warm house, building energy, ~60 min") and Claude assembles an ordered, harmonically sensible playlist from your analysed library. |
| **Saved mixes** | Name and save mixes; they persist between sessions and reload with one click. |
| **Crossfade audition** | The player crossfades the tail of one track into the head of the next (length set in Settings) so you hear the blend, not a hard cut. |
| **Mix script** | Describe transitions in plain English with exact timecodes ("mix track 4 into track 3 at track 3 1:24 / track 4 0:23"); the app beatmatches, warns on big stretches/key clashes, auditions each transition, and renders a continuous mix (crossfade or EQ bass-swap). |
| **Stem separation** *(optional)* | Split a track into vocals / drums / bass / other with Demucs — handy for acapellas & instrumentals. |
| **Export** | Save the finished mix as an **M3U playlist** (download, or straight into your Mixes folder). |

---

## Running from source (development)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python run.py            # opens the desktop app window
python run.py --web      # or run headless and open the printed localhost URL
```

> **Audio libraries:** `librosa` needs a working audio backend. On most systems
> `pip install` handles it; if MP3 decoding fails, install **ffmpeg** and ensure
> it's on your PATH.

---

## First-run setup (in the app's **Settings** tab)

### 1. Google Drive access
The app signs into your own Google account to read the folder you nominate.

1. Go to **Google Cloud Console → APIs & Services**.
2. Enable the **Google Drive API**.
3. **Credentials → Create credentials → OAuth client ID → Application type: Desktop app**.
4. Copy the **Client ID** and **Client secret** into Settings → *Google Drive*, click **Save client**, then **Connect Google Drive** and complete the browser sign-in.
5. Use **Search folder by name** to find and select the folder of tracks.
6. *(Optional)* Set a **Finished-mixes destination folder** — the app uploads
   completed mixes into a `project-mixes` subfolder it creates inside it (via the
   **☁ Save to Drive** button in the Mix Builder).

*Scopes: `drive.readonly` to read your library, plus `drive.file` so the app can
upload finished mixes into folders it creates. It only ever writes files it makes
— it never modifies your existing files. If you connected before this write
feature existed, **disconnect and reconnect** once so the new permission applies.*

### 2. Anthropic API key (for the AI Curator)
Paste your key (`sk-ant-…`) into Settings → *Anthropic*. It's stored **encrypted
on this machine** and only sent to Anthropic when you run the curator. Without a
key, the curator still works using an offline rule-based fallback.

Then open **Library → Analyse Drive folder** to build your analysed library.

---

## Building the Windows installer

### Easiest: let GitHub build it for you (recommended)

PyInstaller can't cross-compile, so the reliable way to get a real `.exe` is to
build on Windows. This repo ships a GitHub Actions workflow
(`.github/workflows/build-windows.yml`) that does exactly that on GitHub's
**Windows runners** — no Windows machine of your own required:

1. On GitHub, open the **Actions** tab → **Build Windows installer** → **Run
   workflow** (or push a tag like `v0.1.0`).
2. When it finishes, download the **`ForTheMix-Windows-Installer`** artifact — it
   contains `ForTheMix-Setup-0.1.0.exe`, ready to run on any Windows desktop.

### Or build locally on a Windows machine with Python installed:

```bat
pip install -r requirements.txt
pyinstaller forthemix.spec
```

This produces `dist\ForTheMix\ForTheMix.exe` (a self-contained folder — no Python
needed on the target machine). To wrap it in a proper installer, install
[Inno Setup](https://jrsoftware.org/isinfo.php) and run:

```bat
iscc installer.iss
```

…which produces `Output\ForTheMix-Setup-0.1.0.exe`, installable on any Windows
desktop.

---

## Where your files live

Everything is kept per-user, outside the install directory. On Windows that's
`%APPDATA%\ForTheMix\`, on macOS `~/Library/Application Support/ForTheMix/`, on
Linux `~/.local/share/ForTheMix/`:

```
ForTheMix/
   settings.json        preferences + Google client id
   secrets.enc          Anthropic API key (encrypted)
   google_token.json    cached Google sign-in
   cache.db             analysis cache + saved mixes
   audio\               downloaded copies of your Drive tracks (the working cache)
   mixes\               ← finished mixes land here (M3U playlists, and copied
                          tracks when you choose "copy tracks")
   stems\               separated stems, grouped per source track
```

**Where do finished mixes go?** When you hit **Export M3U** you get a normal
download; when you hit **Save to folder** the playlist is written to the
`mixes\` folder above (the app shows you the exact path). An `.m3u8` just
references the audio files by path, so keep the source tracks where they are —
or use the "copy tracks" option to bundle numbered copies alongside the
playlist so the mix is fully self-contained and portable.

### Best place to store your local music files

Because you chose "the app signs into Google Drive," **Drive is your source of
truth** — the app downloads what it needs into the `audio\` cache above, so you
don't have to manage local files at all. Recommended setup:

- **Keep your master library in one dedicated Google Drive folder** (e.g.
  `Music/DJ Library`), one nominated folder per crate/genre if you like. Flat
  folders of audio files work best; the app reads the audio files directly in
  the folder you nominate.
- If you'd rather work locally, install **Google Drive for Desktop** and point
  your DJ software at the synced folder — but for ForTheMix itself, nominating
  the Drive folder is all you need.
- **Don't** store your library inside the app's `audio\` cache — that folder is
  managed by the app and may be re-downloaded or cleared. Treat it as scratch.
- Keep originals in a lossless/high-bitrate format where you can; analysis is
  fine on MP3 but stem separation sounds best on higher-quality sources.

---

## Optional power-ups

Both are off by default and enabled from the **Settings** tab once installed:

```bash
pip install -r requirements-optional.txt   # Essentia + Demucs
```

- **Essentia analysis engine** — pro-grade key/BPM detection, plus ML genre
  tagging if you point it at a Discogs-EffNet model. Set **Settings → Analysis
  engine → Essentia**. If Essentia isn't importable the app silently keeps using
  librosa, so nothing breaks.
- **Stem separation (Demucs)** — see the next section.

## Stem separation — research notes

**What it is:** splitting a finished stereo track back into its parts — *vocals,
drums, bass,* and *other* — so you can make acapellas, instrumentals, drum tools,
or do surgical transitions (drop the next track's drums under the current
vocal). It's the same tech behind Spotify/DJ "stem" features.

**Best options in 2026:**

| Tool | Type | Notes |
| --- | --- | --- |
| **Demucs (HTDemucs / htdemucs_ft)** | Open source, local | The de-facto open-source engine; `htdemucs_ft` is the fine-tuned, highest-quality variant. Powers many paid tools. **This is what ForTheMix integrates.** |
| **Mel-RoFormer / MDX-Net** (via Ultimate Vocal Remover) | Open source, local | Among the best for *vocal* isolation specifically; often paired with Demucs for other stems. |
| **RipX / SpectraLayers / RX Music Rebalance** | Paid, desktop | Deep editing suites; best when you need to hand-correct artefacts. |
| **LALAL.ai / Moises / AudioShake** | Paid, cloud | Fast, no local GPU, per-track or subscription pricing; your audio leaves your machine. |

**Why Demucs for this app:** it's free, runs fully locally (your tracks never
leave your machine — matches the app's privacy stance), has a clean Python API,
and quality is competitive with the paid cloud tools. `--two-stems vocals` gives
the fast acapella/instrumental split DJs use most.

**Performance & cost (the catch):**
- **First run downloads a ~300 MB model** (once).
- **GPU vs CPU is night and day:** ~24 s for a 4-minute song on an RTX 3090 vs
  ~4 minutes CPU-only (roughly real-time). A GPU with ≥3 GB VRAM is strongly
  recommended for batch work; CPU is fine for the occasional track.
- Pulls in PyTorch (~1–2 GB install), which is why it's an *optional* extra
  rather than bundled into the base installer.

**How it's wired in ForTheMix:** enable it with `pip install demucs`, then a
🎚 button appears on each mix track; results are written to the `stems\` folder.
Because it's heavy and GPU-dependent, it's marked **experimental** — great as a
prep tool, not something to run mid-set.

*Sources:* [MixingGPT — 8 engines compared](https://mixinggpt.com/blog/best-ai-stem-separation-tools-2026) ·
[Music Production Wiki — best by job](https://musicproductionwiki.com/articles/best-stem-separation-software-2026.html) ·
[Demucs (facebookresearch)](https://github.com/facebookresearch/demucs) ·
[Demucs v4 production guide](https://tomodahinata.com/en/blog/demucs-v4-music-source-separation-production-guide)

## HTTP API (backend)

The local FastAPI server exposes these endpoints (the desktop UI and the mobile
companion talk to the same API). Additive routes for the redesigned UI are marked ✚.

**Library**
- `GET /api/tracks` — list tracks. ✚ Now supports `?offset=&limit=&sort=&dir=&q=&crate=&bpm_min=&bpm_max=` and returns `{ tracks, total, offset, limit }`. With no params it returns every track (unchanged for existing callers).
  - `sort`: `title|artist|genre|bpm|key|energy|duration` (default `title`). `key` orders by Camelot **number then letter** (1A,1B,2A…).
  - `crate`: `all|unanalysed|nogenre|lowconf|dupes`.
- `GET /api/tracks/{id}` — full track incl. waveform peaks.
- `PATCH /api/tracks/{id}` — inline edit. Sets `key_confidence`/`bpm_confidence` to 1.0 and records the fields in `user_edited` so re-analysis won't overwrite them.
- ✚ `PATCH /api/tracks` — bulk edit: `{ "ids": [...], "genre": "…" }` → `{ updated: [...] }`.
- ✚ `GET /api/library/health` → `{ total, unanalysed, missing_genre, low_confidence_key, duplicates }`.

**Analysis job** (progress persists in `cache.db` and resumes after a restart)
- `POST /api/analyze` — start.
- `GET /api/analyze/status` → `{ running, paused, done, total, current, eta_seconds, recent[] }`; `recent` is the last 10 finished files (`{ id, name, key_camelot, bpm, status }`, status = `cached|analysed|tags_only|error`).
- ✚ `POST /api/analyze/pause` · `POST /api/analyze/resume` · `POST /api/analyze/cancel`.

**Audio output device** (Python-side enumeration; needs optional `sounddevice`)
- ✚ `GET /api/audio/devices` → `{ devices: [{ id, name, default }], selected_id, wired, note }`.
- ✚ `POST /api/audio/device` — `{ "id": "…" }`, persisted in `settings.json`. *Note:* the device list and selection are real, but playback isn't routed through Python yet (`wired: false`) — playback is currently browser-side.

**Mixing** (unchanged scoring — the UI mirrors these exactly)
- `POST /api/transitions` — score a sequence (harmonic/tempo/energy). **Weights and thresholds are fixed.**
- ✚ `GET /api/mix` / `PUT /api/mix` — the shared current mix sequence (desktop ⇄ mobile), persisted in `cache.db`.

**Mix script — timecoded transitions → beatmatched render**
- ✚ `POST /api/mixplan/parse` — `{ text, track_ids }` → `{ instructions[], warnings[] }`. Describe transitions in plain English with **explicit timecodes**, one per line, e.g. `mix track 4 into track 3 at track 3 1:24 / track 4 0:23` (add `bass swap` or `crossfade 8s`). Warnings flag big beatmatch stretches and key clashes with options.
- ✚ `POST /api/mixplan/preview` — `{ track_ids, instruction, beatmatch }` → a short rendered WAV of that one transition, to audition the blend.
- ✚ `POST /api/mixplan/render` — `{ track_ids, instructions, name, beatmatch }` → renders the whole continuous mix in the background (see `GET /api/mixplan/render/status`, then `GET /api/mixplan/render/file`). Output WAV lands in the Mixes folder.

The renderer runs the mix at a **constant reference tempo** (the first track's BPM), time-stretching each track to lock beats (pitch preserved via **RubberBand** — **bundled in the Windows installer**, so it works out of the box; otherwise a librosa phase-vocoder fallback), with equal-power crossfades or an **EQ bass-swap**. A beatmatch that needs more than the warn threshold (default **6%**, in Settings) raises a warning with choices before you commit.

> The Windows build's CI step downloads the RubberBand CLI into `vendor/rubberband/`, PyInstaller bundles it beside the app, and it's put on `PATH` at startup. For dev on macOS/Linux, install the CLI (`brew install rubberband` / `apt install rubberband-cli`) for the same quality — without it, rendering uses the automatic librosa fallback.

## Accuracy notes (honest limitations)

- **Key & BPM** from `librosa` are reliable for most electronic/dance material;
  ambient, live, or rhythmically complex tracks are less certain. Low-confidence
  keys are shown with a dashed underline — **you can hand-edit any value**.
- **Genre** is read from each file's embedded tags; tracks without a genre tag
  are shown as *unknown*.
- **Distributing to others:** the Google OAuth client is yours. Sharing the app
  with people outside your Google project would require Google's app-verification
  process. For personal/internal use this isn't needed.

---

## Tech

Python · FastAPI · pywebview · librosa · Google Drive API · Anthropic API ·
vanilla-JS front end (no external CDN — fully offline). Packaged with PyInstaller
+ Inno Setup.
