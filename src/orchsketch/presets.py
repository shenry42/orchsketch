"""Ensemble presets (SPEC §6): built-in ones from data/presets.json, your own in Documents\\OrchSketch\\Presets.

A preset sets the active instruments and the starting points of the global sliders (Forces, Density,
Dynamics; Character stays at Safe until Milestone 5). Roles and patterns are added in Milestone 5.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from .generator import DENSITY_STEPS, DYNAMICS, FORCES, Ensemble
from .instruments import DATA_DIR, DataError, instruments

PRESETS_FILE = DATA_DIR / "presets.json"
USER_PRESETS = Path.home() / "Documents" / "OrchSketch" / "Presets"
DEFAULT_PRESET = "full_epic"


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    instruments: tuple[str, ...]
    forces: str = "section"
    density: int = 5
    dynamics: str = "mf"
    character: str = "safe"
    builtin: bool = False

    def ensemble(self, forces: str | None = None, density: int | None = None,
                 active: frozenset[str] | None = None) -> Ensemble:
        return Ensemble(instruments=active if active is not None else frozenset(self.instruments),
                        forces=forces or self.forces, density=density or self.density)

    def to_json(self) -> dict:
        d = asdict(self)
        d.pop("builtin")
        d["instruments"] = list(self.instruments)
        return d


def parse_preset(raw: dict, name: str = "preset", builtin: bool = False) -> Preset:
    try:
        p = Preset(str(raw["id"]), str(raw["name"]), tuple(raw["instruments"]), raw.get("forces", "section"),
                   int(raw.get("density", 5)), raw.get("dynamics", "mf"), raw.get("character", "safe"), builtin)
    except (KeyError, TypeError, ValueError) as exc:
        raise DataError(f"{name}: {exc}") from None
    insts = instruments()
    bad = [i for i in p.instruments if i not in insts]
    if bad:
        raise DataError(f"{name}: unknown instrument(s) {', '.join(bad)}")
    if not p.instruments:
        raise DataError(f"{name}: no instruments")
    if p.forces not in FORCES or p.density not in DENSITY_STEPS or p.dynamics not in DYNAMICS:
        raise DataError(f"{name}: forces, density or dynamics out of range")
    if p.character != "safe":
        raise DataError(f"{name}: character must be 'safe' until Milestone 5")
    return p


@lru_cache(maxsize=1)
def builtin_presets() -> tuple[Preset, ...]:
    raw = json.loads(PRESETS_FILE.read_text(encoding="utf-8"))
    return tuple(parse_preset(r, PRESETS_FILE.name, builtin=True) for r in raw["presets"])


def preset_id(name: str) -> str:
    return "user_" + (re.sub(r"[^A-Za-z0-9]+", "_", name.strip()).strip("_").lower() or "preset")


def user_presets(folder: Path | None = None) -> list[Preset]:
    """Your saved presets. A broken file is skipped (and listed in the second return value of load_all)."""
    return load_all(folder)[0][len(builtin_presets()):]


def load_all(folder: Path | None = None) -> tuple[list[Preset], list[str]]:
    """Built-in presets followed by yours (sorted by name), plus messages for files that couldn't be read."""
    folder = folder or USER_PRESETS
    out, problems = list(builtin_presets()), []
    if folder.is_dir():
        mine = []
        for f in sorted(folder.glob("*.json")):
            try:
                mine.append(parse_preset(json.loads(f.read_text(encoding="utf-8")), f.name))
            except (OSError, ValueError) as exc:
                problems.append(f"{f.name}: {exc}")
        out += sorted(mine, key=lambda p: p.name.lower())
    return out, problems


def save_preset(preset: Preset, folder: Path | None = None) -> Path:
    folder = folder or USER_PRESETS
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{preset.id}.json"
    path.write_text(json.dumps(preset.to_json(), indent=2), encoding="utf-8")
    return path


def find(presets, pid: str) -> Preset | None:
    return next((p for p in presets if p.id == pid), None)
