"""Locate the bundled FluidSynth DLLs and SoundFont, and make pyfluidsynth able to load them.

Call prepare() before `import fluidsynth`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _search_roots() -> list[Path]:
    roots = []
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        roots.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)))
        roots.append(Path(sys.executable).parent)
    roots.append(PROJECT_ROOT / "vendor")
    return roots


def find_dll_dir() -> Path:
    for root in _search_roots():
        if root.exists():
            for dll in root.rglob("libfluidsynth*.dll"):
                return dll.parent
    raise FileNotFoundError("FluidSynth DLL not found. Run scripts\\setup.bat.")


def find_soundfont() -> Path:
    for root in _search_roots():
        for cand in (root / "GeneralUser-GS.sf2", root / "soundfonts" / "GeneralUser-GS.sf2"):
            if cand.exists():
                return cand
    raise FileNotFoundError("GeneralUser-GS.sf2 not found. Run scripts\\setup.bat.")


def prepare() -> Path:
    """Put the FluidSynth DLL folder on the DLL search path. Returns that folder."""
    dll_dir = find_dll_dir()
    os.environ["FLUIDSYNTH_PATH"] = str(dll_dir)
    os.environ["PATH"] = str(dll_dir) + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(dll_dir))
    return dll_dir
