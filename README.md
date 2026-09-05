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
| **Export** | Save the finished mix as an **M3U playlist** for any player or DJ software. |

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

*Read-only Drive scope is requested — the app never modifies your Drive.*

### 2. Anthropic API key (for the AI Curator)
Paste your key (`sk-ant-…`) into Settings → *Anthropic*. It's stored **encrypted
on this machine** and only sent to Anthropic when you run the curator. Without a
key, the curator still works using an offline rule-based fallback.

Then open **Library → Analyse Drive folder** to build your analysed library.

---

## Building the Windows installer

On a Windows machine with Python installed:

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

## Where your data lives

Everything is kept per-user, outside the install directory:

```
%APPDATA%\ForTheMix\
   settings.json        preferences + Google client id
   secrets.enc          Anthropic API key (encrypted)
   google_token.json    cached Google sign-in
   cache.db             analysis cache
   audio\               downloaded tracks
```

---

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
