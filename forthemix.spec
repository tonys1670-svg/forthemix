# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ForTheMix.

Build with:  pyinstaller forthemix.spec
Produces:    dist/ForTheMix/ForTheMix.exe  (one-folder build; onedir is more
             reliable than onefile for scientific libs like librosa/numba).
"""
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = []
datas = [("app/frontend", "frontend")]

# librosa / numba / sklearn pull in data and lazy submodules PyInstaller misses.
for pkg in ("librosa", "sklearn", "google_auth_oauthlib", "googleapiclient"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass
for pkg in ("librosa", "sklearn.utils", "anthropic", "googleapiclient"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass
hiddenimports += ["sklearn.utils._typedefs", "sklearn.neighbors._partition_nodes"]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
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
