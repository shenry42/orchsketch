"""Expression (SPEC §14 milestone 9, v1.4): CC1/CC11 curves, swells, velocity shaping, section balance, humanize,
and the helpers for tremolo and riser parts. No UI code.

Everything here is render-only and off by default; with every option off the orchestration and its export are
exactly v1.3's (tests/test_expression.py compares the exported bytes).

CC curves (Settings.curves, or any Swell)
    Stored per part in Orchestration.meta["expression"]["curves"] as breakpoints [tick, controller, value],
    worked out when the orchestration is rendered, so a saved project reopens with exactly the same curves.
    CC1 (the library's dynamics) follows the part's level bar by bar: its section's Dynamics, plus the
    intensity shape's step for that bar (the same steps that set velocity, shapes.bar_steps), plus Balance.
    A rising level ramps in over the last beat before the bar (over the whole bar when it keeps rising, as in
    Build); a falling one drops at the bar line (or ramps over the bar when it keeps falling, as in Swell).
    On top of that:
      * strings and choir: a crescendo/diminuendo over every phrase (Phrase setting) on CC1
      * woodwinds and brass: one CC11 (expression) arc per phrase, 100 at the phrase ends and 127 in the middle
        (SPEC §14); their CC1 follows the level only. Strings and choir hold CC11 at 127.
      * a small swell inside every chord of a half note or longer that the part holds
      * Swells (per section): CC1 dips and swells into the next chord ("chord") or only into the downbeat of
        the next phrase ("downbeat"), over the chord's last beat (its last half, at most a bar)
      * risers: CC1 rises through the riser; in the Shepard-style riser the bottom layer fades in and the top
        layer fades out on CC11
    The export writes the curves instead of the constant CC1 (thinned: one event per 16th at most, only where
    the value changes). The audition can't play CC1 as dynamics (General MIDI uses it for vibrato), so each
    channel's expression (CC11) follows its parts' curve, relative to the part's loudest point.

Velocity shaping (Settings.phrase_arcs, Settings.beat_accents)
    Phrase arcs: velocities rise toward the middle of every phrase and fall back (x0.92 .. x1.08).
    Beat accents: beat 1 strongest, then beat 3, beats 2 and 4 a little under, off-beats a little more under.

Balance sections (Settings.balance): data/balance.json, dynamic steps per section (woodwinds one under).

Humanize (Settings.humanize: off / light / medium): seeded timing and velocity offsets, applied only where notes
leave the app (export and audition): the grid, the checker and the saved notes stay on the grid. The same
orchestration always gets the same offsets (seed, alternative and part).
"""
from __future__ import annotations

import json
import math
import random
from functools import lru_cache
from pathlib import Path

from .midi_io import BAR, PPQ, Note

DATA = Path(__file__).resolve().parent / "data"
BALANCE_FILE = DATA / "balance.json"

SIXTEENTH = PPQ // 4
CC_DYNAMICS, CC_EXPRESSION = 1, 11

SWELL_OFF, SWELL_CHORD, SWELL_DOWNBEAT = "off", "chord", "downbeat"
SWELLS = (SWELL_OFF, SWELL_CHORD, SWELL_DOWNBEAT)
SWELL_NAMES = {SWELL_OFF: "Off", SWELL_CHORD: "Into every chord", SWELL_DOWNBEAT: "Into phrase downbeats"}

HUMANIZE_OFF = "off"
HUMANIZE = (HUMANIZE_OFF, "light", "medium")
HUMANIZE_NAMES = {HUMANIZE_OFF: "Off", "light": "Light", "medium": "Medium"}
HUMANIZE_AMOUNT = {"light": (6, 4), "medium": (12, 7)}  # (timing ticks at 480 PPQ, velocity), each +/-

RISER_BARS = (0, 1, 2, 4)
RISER_SECTIONS = ("strings", "woodwinds")
TREMOLO = "tremolo"  # the tremolo pattern (data/patterns/tremolo.json): its notes export as their own part
TREMOLO_PROGRAM = 44  # GM Tremolo Strings, for audition
KINDS = ("", "trem", "rise")  # main part, tremolo part, riser part
KIND_EXPORT = {"trem": "-trem", "rise": "-rise"}  # export code suffix
KIND_LABEL = {"trem": " trem", "rise": " riser"}

CC11_SECTIONS = ("woodwinds", "brass")  # one CC11 arc per phrase (SPEC §14)
PHRASE_ARC = 10  # CC1 crescendo/diminuendo over a phrase (strings, choir): -5 .. +5 around the level
CC11_LOW = 100  # CC11 at the phrase ends (winds, brass); 127 in the middle
CHORD_SWELL = 4  # a small swell inside held chords of a half note or longer
SWELL_FROM, SWELL_TO = -10, 16  # Swells: CC1 offset at the start and the end of the swell
RISER_FROM, RISER_TO = -24, 16  # riser: CC1 offset from its start to the hit
SHEPARD_LOW = 40  # Shepard riser: the fading layers' CC11 floor
ARC_VEL = (0.88, 0.24)  # phrase arcs: velocity factor = a + b * sin(pi * x) (v1.4 tuning: was 0.92 + 0.16)
BEAT_VEL = {0: 1.15, 2 * PPQ: 1.06, PPQ: 0.92, 3 * PPQ: 0.92}  # beat accents; other positions OFFBEAT_VEL
OFFBEAT_VEL = 0.86  # (v1.4 tuning: Sam couldn't hear 1.08 / 1.03 / 0.97 / 0.95)
TAPER = -20  # CC1 over the last bar of a section that a shape takes out next bar (Breakdown)
AUDITION_VOLUME = {TREMOLO_PROGRAM: 127}  # audition only: CC7 per GM program (GM default 100); tremolo is quiet


# ---------------------------------------------------------------- data
@lru_cache(maxsize=1)
def balance_table() -> dict[str, int]:
    raw = json.loads(BALANCE_FILE.read_text(encoding="utf-8"))
    steps = {str(k): int(v) for k, v in raw["steps"].items()}
    if any(v > 0 for v in steps.values()):
        raise ValueError("balance.json: steps only lower a section (0 or negative)")
    return steps


def balance_step(section: str, on: bool) -> int:
    return balance_table().get(section, 0) if on else 0


def clamp(v: float, lo: int = 1, hi: int = 127) -> int:
    return max(lo, min(hi, int(round(v))))


def phrase_pos(t: int, phrase: int) -> float:
    """Position 0..1 of tick t inside its phrase."""
    length = phrase * BAR
    return (t % length) / length


# ---------------------------------------------------------------- velocity shaping
def shape_velocities(notes, phrase: int, arcs: bool, accents: bool, factor: float = 1.0) -> list[Note]:
    """Phrase arcs and beat accents on one part's notes; `factor` scales every velocity (Balance)."""
    out = []
    for n in notes:
        f = factor
        if arcs:
            f *= ARC_VEL[0] + ARC_VEL[1] * math.sin(math.pi * phrase_pos(n.start, phrase))
        if accents:
            f *= BEAT_VEL.get(n.start % BAR, OFFBEAT_VEL)
        out.append(n if f == 1.0 else Note(n.pitch, n.start, n.end, clamp(n.velocity * f)))
    return out


# ---------------------------------------------------------------- curves
def _base(values: list[int], t: int) -> float:
    """The level at tick t from per-bar values, with the ramps described in the module docstring."""
    nb = len(values)
    b = min(t // BAR, nb - 1)
    v = values[b]
    if b + 1 < nb:
        d = values[b + 1] - v
        if d:
            prev = v - values[b - 1] if b > 0 else 0
            if d > 0:
                ramp = BAR if prev > 0 else PPQ
            else:
                ramp = BAR if prev < 0 else 0
            start = (b + 1) * BAR - ramp
            if ramp and t >= start:
                return v + d * (t - start) / ramp
    return v


def curve(values: list[int], section: str, notes, chord_bounds: list[tuple[int, int]], length: int, phrase: int,
          swell: str = SWELL_OFF, riser: tuple | None = None, tapers=()) -> list[list[int]]:
    """Breakpoints [tick, controller, value] for one part (CC1 and CC11).

    values: CC1 level per bar. chord_bounds: (start, end) per chord. riser: (start, end, layer, layers).
    tapers: (start, end) spans where the part fades out before a shape takes its section out."""
    held: list[tuple[int, int]] = []  # chords the part holds (one note over most of a chord of 2+ beats)
    for a, z in chord_bounds:
        if z - a >= 2 * PPQ and any(n.start <= a + SIXTEENTH and n.end >= z - SIXTEENTH and n.end - n.start
                                    >= (z - a) * 3 // 4 for n in notes):
            held.append((a, z))
    swells: list[tuple[int, int]] = []
    if swell != SWELL_OFF:
        for (a, z), nxt in zip(chord_bounds, chord_bounds[1:]):
            if nxt[0] != z:
                continue
            if swell == SWELL_DOWNBEAT and z % (phrase * BAR):
                continue
            r = min(BAR, max(PPQ, (z - a) // 2))
            swells.append((z - r, z))
    cc11_arc = section in CC11_SECTIONS
    out: list[list[int]] = []
    last = {CC_DYNAMICS: None, CC_EXPRESSION: None}
    for t in range(0, max(length, SIXTEENTH), SIXTEENTH):
        v = _base(values, t)
        x = phrase_pos(t, phrase)
        if not cc11_arc:
            v += PHRASE_ARC * (math.sin(math.pi * x) - 0.5)
        for a, z in held:
            if a <= t < z:
                v += CHORD_SWELL * math.sin(math.pi * (t - a) / (z - a))
        for a, z in swells:
            if a <= t < z:
                f = (t - a) / (z - a)
                v += SWELL_FROM + (SWELL_TO - SWELL_FROM) * f * f
        for a, z in tapers:
            if a <= t < z:
                v += TAPER * (t - a) / (z - a)
        e = 127.0 - (127 - CC11_LOW) * (1 - math.sin(math.pi * x)) if cc11_arc else 127.0
        if riser is not None and riser[0] <= t < riser[1]:
            f = (t - riser[0]) / (riser[1] - riser[0])
            v += RISER_FROM + (RISER_TO - RISER_FROM) * f
            layer, layers = riser[2], riser[3]
            if layers > 1 and layer == 0:
                e = 127 - (127 - SHEPARD_LOW) * f  # the top layer fades out
            elif layers > 1 and layer == layers - 1:
                e = SHEPARD_LOW + (127 - SHEPARD_LOW) * f  # the bottom layer fades in
        for cc, val in ((CC_DYNAMICS, clamp(v)), (CC_EXPRESSION, clamp(e))):
            if val != last[cc]:
                out.append([t, cc, val])
                last[cc] = val
    return out


def cc_at(points, cc: int, t: int, default: int) -> int:
    """The controller's value at tick t from breakpoints."""
    v = default
    for pt, c, val in points:
        if pt > t:
            break
        if c == cc:
            v = val
    return v


def audition_expression(points) -> list[tuple[int, int]]:
    """(tick, CC11) for the audition: CC1 relative to the part's loudest point (square root, so a shape's
    quiet bars don't vanish: velocity already carries the level), times the part's CC11."""
    if not points:
        return []
    ref = max((v for _, c, v in points if c == CC_DYNAMICS), default=127)
    out = []
    d, e = ref, 127
    last = None
    for t, c, v in points:
        if c == CC_DYNAMICS:
            d = v
        else:
            e = v
        val = clamp(127 * math.sqrt(d / ref) * e / 127)
        if out and out[-1][0] == t:
            out[-1] = (t, val)
        elif val != last:
            out.append((t, val))
        last = out[-1][1] if out else None
    return out


# ---------------------------------------------------------------- humanize
def humanize(notes, key: str, amount: str) -> list[Note]:
    """Seeded timing and velocity offsets (export and audition only). Ends stay put (legato and chord changes
    keep their shape); no note starts before bar 1 or overlaps the next note on its pitch."""
    if amount == HUMANIZE_OFF or not notes:
        return list(notes)
    dt, dv = HUMANIZE_AMOUNT[amount]
    rnd = random.Random(key)
    shifted = []
    for n in sorted(notes, key=lambda n: (n.start, n.pitch, n.end)):
        s = max(0, n.start + rnd.randint(-dt, dt))
        s = min(s, n.end - SIXTEENTH // 4) if n.end - n.start > SIXTEENTH // 4 else n.start
        shifted.append(Note(n.pitch, s, n.end, clamp(n.velocity + rnd.randint(-dv, dv))))
    by_pitch: dict[int, list[int]] = {}
    for k, n in enumerate(shifted):
        by_pitch.setdefault(n.pitch, []).append(k)
    for ks in by_pitch.values():
        ks.sort(key=lambda k: shifted[k].start)
        for a, b in zip(ks, ks[1:]):
            pa, pb = shifted[a], shifted[b]
            if pa.end > pb.start:
                shifted[a] = Note(pa.pitch, pa.start, max(pa.start + 1, pb.start), pa.velocity)
    return sorted(shifted, key=lambda n: (n.start, -n.pitch))


def humanize_key(seed: int, alt: str, line_id: str, kind: str = "") -> str:
    return f"{seed}/{alt}/{line_id}/{kind}"


# ---------------------------------------------------------------- tremolo and riser parts
def spans_of(meta: dict, kind: str, line_id: str) -> list[tuple[int, int]]:
    ex = meta.get("expression") or {}
    if kind == "trem":
        return [tuple(x) for x in (ex.get("trem") or {}).get(line_id, ())]
    if kind == "rise":
        r = (ex.get("rise") or {}).get(line_id)
        return [(r[0], r[1])] if r else []
    return []


def split_notes(meta: dict, line_id: str, notes) -> dict[str, list[Note]]:
    """A part's notes by export kind: "" (the part), "trem" (its tremolo notes), "rise" (its riser notes)."""
    out = {k: [] for k in KINDS}
    trem = spans_of(meta, "trem", line_id)
    rise = spans_of(meta, "rise", line_id)
    for n in notes:
        if any(a <= n.start < b for a, b in rise):
            out["rise"].append(n)
        elif any(a <= n.start < b for a, b in trem):
            out["trem"].append(n)
        else:
            out[""].append(n)
    return out


def curves_of(meta: dict, line_id: str):
    return ((meta.get("expression") or {}).get("curves") or {}).get(line_id)


def riser_pitches(target: int, count: int, steps: int, scales: list[set[int]], ok, step_pitch) -> list[int] | None:
    """A rising line of `count` notes ending one scale step (at least) under `target`, `steps` scale steps from
    its first note to the target; each note in its own chord's scale, never falling. None if a note doesn't fit."""
    out: list[int] = []
    for k in range(count):
        off = steps - (steps * k) // count
        q = step_pitch(target, -off, scales[k])
        if q is None:
            return None
        if out and q < out[-1]:
            q = out[-1] if out[-1] % 12 in scales[k] else step_pitch(out[-1], 1, scales[k])
            if q is None:
                return None
        if q >= target or not ok(q):
            return None
        out.append(q)
    return out
