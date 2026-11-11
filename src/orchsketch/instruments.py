"""Instrument records (SPEC §4), loaded from data/instruments/*.json.

All pitches are sounding (concert) pitch. The JSON files use scientific names (C4 = middle C);
records hold MIDI numbers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .theory import note_name, parse_pitch

DATA_DIR = Path(__file__).resolve().parent / "data"
INSTRUMENT_DIR = DATA_DIR / "instruments"

SECTIONS = ("woodwinds", "brass", "strings", "choir")
ROLES = ("bass", "low_harmony", "mid_harmony", "high_harmony", "melody", "pad")
_FIELDS = {"id", "name", "short", "section", "order", "playable", "comfortable", "default_count",
           "max_divisi", "gm_program", "roles", "registers", "audition_note"}


class DataError(ValueError):
    """A data file is wrong. The message names the file and the field."""


@dataclass(frozen=True)
class Register:
    low: int
    high: int
    note: str


@dataclass(frozen=True)
class Instrument:
    id: str
    name: str
    short: str
    section: str
    order: int
    playable: tuple[int, int]
    comfortable: tuple[int, int]
    default_count: int | str  # a number of players, or "section"
    max_divisi: int
    gm_program: int  # 0-127, as written to MIDI
    roles: tuple[str, ...]
    registers: tuple[Register, ...]
    audition_note: str = ""

    def is_playable(self, pitch: int) -> bool:
        return self.playable[0] <= pitch <= self.playable[1]

    def is_comfortable(self, pitch: int) -> bool:
        return self.comfortable[0] <= pitch <= self.comfortable[1]

    def register_notes(self, pitch: int) -> list[str]:
        return [r.note for r in self.registers if r.low <= pitch <= r.high]

    def range_text(self, which: str = "playable", style: str = "ableton") -> str:
        lo, hi = getattr(self, which)
        return f"{note_name(lo, style)}–{note_name(hi, style)}"


def _pair(path: Path, field: str, value) -> tuple[int, int]:
    if not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, str) for v in value)):
        raise DataError(f"{path.name}: '{field}' must be two pitch names, e.g. [\"C4\", \"A6\"]")
    try:
        lo, hi = parse_pitch(value[0]), parse_pitch(value[1])
    except ValueError as exc:
        raise DataError(f"{path.name}: '{field}': {exc}") from None
    if lo > hi:
        raise DataError(f"{path.name}: '{field}' low note is above the high note")
    return lo, hi


def parse_instrument(raw: dict, path: Path = Path("<data>")) -> Instrument:
    missing = (_FIELDS - {"audition_note"}) - raw.keys()
    if missing:
        raise DataError(f"{path.name}: missing {', '.join(sorted(missing))}")
    unknown = raw.keys() - _FIELDS
    if unknown:
        raise DataError(f"{path.name}: unknown field(s) {', '.join(sorted(unknown))}")
    if path.suffix == ".json" and raw["id"] != path.stem:
        raise DataError(f"{path.name}: id '{raw['id']}' doesn't match the file name")
    if raw["section"] not in SECTIONS:
        raise DataError(f"{path.name}: section must be one of {', '.join(SECTIONS)}")
    playable = _pair(path, "playable", raw["playable"])
    comfortable = _pair(path, "comfortable", raw["comfortable"])
    if not (playable[0] <= comfortable[0] and comfortable[1] <= playable[1]):
        raise DataError(f"{path.name}: comfortable range must lie inside the playable range")
    count = raw["default_count"]
    if not (count == "section" or (isinstance(count, int) and count >= 1)):
        raise DataError(f"{path.name}: default_count must be a number of players or \"section\"")
    if not (isinstance(raw["max_divisi"], int) and 1 <= raw["max_divisi"] <= 4):
        raise DataError(f"{path.name}: max_divisi must be 1-4")
    if not (isinstance(raw["gm_program"], int) and 0 <= raw["gm_program"] <= 127):
        raise DataError(f"{path.name}: gm_program must be 0-127")
    roles = tuple(raw["roles"])
    bad = [r for r in roles if r not in ROLES]
    if not roles or bad:
        raise DataError(f"{path.name}: roles must be from {', '.join(ROLES)}")
    regs = []
    for i, reg in enumerate(raw["registers"]):
        lo, hi = _pair(path, f"registers[{i}].range", reg.get("range"))
        if not (playable[0] <= lo and hi <= playable[1]):
            raise DataError(f"{path.name}: registers[{i}] goes outside the playable range")
        regs.append(Register(lo, hi, str(reg.get("note", ""))))
    return Instrument(
        id=raw["id"], name=raw["name"], short=raw["short"], section=raw["section"],
        order=int(raw["order"]), playable=playable, comfortable=comfortable, default_count=count,
        max_divisi=raw["max_divisi"], gm_program=raw["gm_program"], roles=roles,
        registers=tuple(regs), audition_note=raw.get("audition_note", ""),
    )


def load_instruments(directory: Path | str | None = None) -> dict[str, Instrument]:
    """All instruments, in score order (woodwinds, brass, strings, choir)."""
    d = Path(directory) if directory else INSTRUMENT_DIR
    out: dict[str, Instrument] = {}
    for path in sorted(d.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DataError(f"{path.name}: not valid JSON ({exc})") from None
        inst = parse_instrument(raw, path)
        out[inst.id] = inst
    if not out:
        raise DataError(f"no instrument files in {d}")
    return dict(sorted(out.items(), key=lambda kv: kv[1].order))


@lru_cache(maxsize=1)
def instruments() -> dict[str, Instrument]:
    """The built-in instrument set (cached)."""
    return load_instruments()


def get(instrument_id: str) -> Instrument:
    try:
        return instruments()[instrument_id]
    except KeyError:
        raise KeyError(f"unknown instrument '{instrument_id}'") from None
