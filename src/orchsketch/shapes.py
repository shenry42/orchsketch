"""Intensity shapes (SPEC §14 milestone 8): presets that change density, forces, pattern and dynamics bar by
bar. Shapes are data, one JSON file per shape in data/shapes/.

The settings are the shape's peak: every step lowers them (offsets are 0 or negative), so a shape never asks
for lines the voicing search didn't place. That keeps shapes render-only: they change instantly, like
Dynamics and Pattern, and the harmony (and its speed) is untouched.

A shape file
    id, name, order (menu order), description
    span        "clip": the steps are stretched over the whole clip; "phrase": over every phrase (2, 4 or 8
                bars, the Phrase setting), repeating; "layers": one step per 4 bars (clips under 16 bars: per
                quarter of the clip)
    last_bar_only  the last step is the clip's last bar only (Build and hit); the others share the rest
    steps       one dict per step, all keys optional:
        density   Density steps down (-1 ... -4; at least 1)
        forces    -1: Divisi plays as Section (one line per string instrument); Section and Solo stay
        dynamics  dynamic steps down (pp is the floor)
        pattern   pattern levels down (16ths -> 8ths -> half-time -> Sustain; patterns.step_down)
        sections  only this many sections play, in the order strings, brass, woodwinds, choir
        entering  dynamic steps for the last of those sections (the one that just came in; Pulse bed)
        hit       every part plays one hit on the bar's downbeat (pattern "hit_downbeat")
        dropout   every part rests on the last 8th of the step's last bar (air before the next downbeat)

The generator's render step applies the steps (generator._render) and checks every chord: where a step would
break a rule (for example a voice left with nothing to play), that chord plays as set instead.
No UI code.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

SHAPE_DIR = Path(__file__).resolve().parent / "data" / "shapes"
STEADY = "steady"
PHRASES = (2, 4, 8)
SECTION_ORDER = ("strings", "brass", "woodwinds", "choir")  # "sections": n keeps the first n present


class ShapeError(ValueError):
    pass


@dataclass(frozen=True)
class Step:
    density: int = 0
    forces: int = 0
    dynamics: int = 0
    pattern: int = 0
    sections: int | None = None
    hit: bool = False
    dropout: bool = False
    entering: int = 0

    @property
    def changes_lines(self) -> bool:
        return bool(self.density or self.forces or self.sections is not None)

    @property
    def neutral(self) -> bool:
        return self == Step()


NEUTRAL = Step()


@dataclass(frozen=True)
class Shape:
    id: str
    name: str
    order: int
    span: str
    steps: tuple[Step, ...]
    last_bar_only: bool = False
    description: str = ""


def _step(raw: dict, name: str) -> Step:
    bad = set(raw) - {"density", "forces", "dynamics", "pattern", "sections", "hit", "dropout", "entering"}
    if bad:
        raise ShapeError(f"{name}: unknown step key(s) {', '.join(sorted(bad))}")
    st = Step(int(raw.get("density", 0)), int(raw.get("forces", 0)), int(raw.get("dynamics", 0)),
              int(raw.get("pattern", 0)), None if raw.get("sections") is None else int(raw["sections"]),
              bool(raw.get("hit", False)), bool(raw.get("dropout", False)), int(raw.get("entering", 0)))
    if st.density > 0 or st.dynamics > 0 or st.pattern > 0 or st.entering > 0 or st.forces not in (0, -1):
        raise ShapeError(f"{name}: steps only lower the settings (density, dynamics, pattern, entering <= 0; forces 0 or -1)")
    if st.sections is not None and not 1 <= st.sections <= len(SECTION_ORDER):
        raise ShapeError(f"{name}: sections is 1-4")
    return st


@lru_cache(maxsize=1)
def library() -> dict[str, Shape]:
    out = {}
    for path in sorted(SHAPE_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            span = raw.get("span", "clip")
            if span not in ("clip", "phrase", "layers"):
                raise ShapeError(f"{path.name}: span must be clip, phrase or layers")
            steps = tuple(_step(s, path.name) for s in raw["steps"])
            if not steps:
                raise ShapeError(f"{path.name}: a shape needs at least one step")
            sh = Shape(str(raw["id"]), str(raw["name"]), int(raw.get("order", 99)), span, steps,
                       bool(raw.get("last_bar_only", False)), str(raw.get("description", "")))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, ShapeError):
                raise
            raise ShapeError(f"{path.name}: {type(exc).__name__}: {exc}") from None
        if sh.id in out:
            raise ShapeError(f"{path.name}: shape id {sh.id!r} is used twice")
        out[sh.id] = sh
    if STEADY not in out:
        raise ShapeError("data/shapes is missing steady.json")
    return dict(sorted(out.items(), key=lambda kv: (kv[1].order, kv[0])))


SHAPES = tuple(library())
SHAPE_NAMES = {k: s.name for k, s in library().items()}


def bar_steps(shape_id: str, bars: int, phrase: int = 4) -> list[Step]:
    """The step that applies to each bar of a clip `bars` long. `dropout` only stays on the last bar of the
    bars a step covers."""
    sh = library()[shape_id]
    n = len(sh.steps)
    if bars <= 0:
        return []
    if sh.id == STEADY or all(s.neutral for s in sh.steps):
        return [NEUTRAL] * bars
    idx: list[int] = []
    if sh.span == "phrase":
        # the phrase's last bar always takes the last step (its drop-out leads into the next phrase)
        idx = [n - 1 if b % phrase == phrase - 1 else (b % phrase) * n // phrase for b in range(bars)]
    elif sh.span == "layers":
        size = 4 if bars >= 16 else max(1, bars // 4)
        idx = [min(b // size, n - 1) for b in range(bars)]
    elif sh.last_bar_only and bars > 1:
        idx = [b * (n - 1) // (bars - 1) for b in range(bars - 1)] + [n - 1]
    else:
        idx = [b * n // bars for b in range(bars)]
    out = []
    for b, k in enumerate(idx):
        st = sh.steps[k]
        if st.dropout:
            last_of_range = b + 1 >= bars or idx[b + 1] != k or (sh.span == "phrase" and (b + 1) % phrase == 0)
            if not last_of_range:
                st = Step(st.density, st.forces, st.dynamics, st.pattern, st.sections, st.hit, False, st.entering)
        out.append(st)
    return out
