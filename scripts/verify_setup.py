"""Checks the dev environment after setup.bat. Exit code 0 = all good."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ok = True


def check(label, fn):
    global ok
    try:
        print(f"OK   {label}: {fn()}")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"FAIL {label}: {exc!r}")


check("python", lambda: sys.version.split()[0] + (" (needs 3.12)" if sys.version_info[:2] != (3, 12) else ""))
check("mido", lambda: (__import__("mido"), __import__("importlib.metadata").metadata.version("mido"))[1])
check("PySide6", lambda: __import__("PySide6").__version__)
check("pytest", lambda: __import__("pytest").__version__)
check("music21", lambda: str(__import__("music21").VERSION_STR))
check("PyInstaller", lambda: __import__("PyInstaller").__version__)

sys.path.insert(0, str(ROOT / "src"))


def _fs():
    from orchsketch.playback import fluid_env
    path = fluid_env.prepare()
    import fluidsynth  # noqa: F401
    return str(path)


def _sf():
    sf = ROOT / "vendor" / "soundfonts" / "GeneralUser-GS.sf2"
    if not sf.exists():
        raise FileNotFoundError(sf)
    return f"{sf.stat().st_size / 1e6:.1f} MB"


check("FluidSynth DLL + pyfluidsynth", _fs)
check("SoundFont", _sf)
print("ALL OK" if ok else "SOME CHECKS FAILED")
sys.exit(0 if ok else 1)
