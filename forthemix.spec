# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ForTheMix.

Build with:  pyinstaller forthemix.spec
Produces:    dist/ForTheMix/ForTheMix.exe  (one-folder build; onedir is more
             reliable than onefile for scientific libs like librosa/numba).
"""
import glob
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

hiddenimports = []
datas = [("app/frontend", "frontend")]  # includes frontend/fonts (recursive)
binaries = []

# librosa / numba / sklearn pull in data and lazy submodules PyInstaller misses.
for pkg in ("librosa", "sklearn", "google_auth_oauthlib", "googleapiclient", "soundfile"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass
for pkg in ("librosa", "sklearn.utils", "anthropic", "googleapiclient", "scipy.signal"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass
hiddenimports += ["sklearn.utils._typedefs", "sklearn.neighbors._partition_nodes",
                  "soundfile", "pyrubberband", "scipy.signal"]

# soundfile ships libsndfile as a bundled dynamic library.
for pkg in ("soundfile", "scipy"):
    try:
        binaries += collect_dynamic_libs(pkg)
    except Exception:
        pass

# Bundle the RubberBand CLI (rubberband.exe + any DLLs) if the CI step fetched it
# into vendor/rubberband/. pyrubberband shells out to it; main.py puts it on PATH.
if os.path.isdir("vendor/rubberband"):
    for f in glob.glob("vendor/rubberband/*"):
        if os.path.isfile(f):
            binaries.append((f, "rubberband"))

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ForTheMix",
    console=False,
    icon="build_assets/icon.ico" if __import__("os").path.exists("build_assets/icon.ico") else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ForTheMix")
