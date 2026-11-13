"""Rhythm patterns (SPEC §5c, §14 milestone 7): turn one pitch per part per chord into notes.

Patterns are data: one JSON file per pattern in data/patterns/, accent groupings in data/accents.json. A new
pattern needs a new file, no engine code. Patterns are applied after the voicings are chosen (SPEC §5 step 5),
so they never change which pitch a part plays at a chord change: every pattern strikes the part's own note
(the *anchor*) at the start of each chord.

A pattern file
    id, name, short (grid tag), order (menu order), family (pattern alternatives pick within a family),
    kind        "sustain", "grid" (a note on every 8th or 16th) or "hits" (notes at given points of the bar)
    step        grid: "8th" or "16th"
    hits        hits: 16th positions in the bar; `length` (16ths) is each hit's length, cut at the next hit
    accents     16th positions in the bar that are accented (others play at 80%; hits without the list are
                all accented)
    contour     one step offset per note, counted from the chord's start and repeated (0 = the anchor). What
                one step means is the section's note mode (below). The first entry must be 0.
    octaves     optional octave shifts per note, repeated like the contour
    min_step    chord-tone steps go at least this many semitones from the anchor (16ths alternating: 3)
    end_on_anchor  the chord's last note is the anchor again, so the move into the next chord is exactly
                Sustain's (the checker's chord-change rules see what the voicing search chose)
    passing     moderate mode may end the chord on a passing tone (the v1 8th and 16th ostinatos)
    choir       choirs may sing it
    note_mode   optional: always this note mode, whatever the section's (arpeggios: "chord")
    degrees     the contour counts chord degrees above the anchor instead of steps: 3 (a 3rd), 5 (a 5th),
                8 (the octave), 10 (a 10th), each the nearest chord tone to that interval (v1.3 arpeggios)
    anticipate  hits patterns: the next chord is struck an 8th early and tied over (v1.3 stabs); the
                generator checks that 8th against what still sounds, and strikes on the beat where it fails
    down        the next quieter pattern for intensity shapes (v1.3); default by family: 16ths -> 8ths ->
                half-time -> Sustain

Note modes (per section; SPEC §14 decision)
    chord   Chord tones (default): every step is the next chord tone, so every note is consonant.
    hybrid  Hybrid: steps follow the chord's scale; notes on a beat or an accent snap to the nearest chord tone.
    scale   Scale steps: steps follow the chord's scale (the key's scale with the chord's own tones put in).
A note that falls outside the part's range is mirrored (a step down instead of up, an octave down instead of
up); if that doesn't fit either, the anchor is played.

Accent groupings (data/accents.json) replace a grid pattern's own accents: the first note of every group is
accented, the others play at 80% velocity and, for the "short" groupings, at a shorter length.

The six v1 patterns render exactly as in v1.1 (tests/test_patterns.py compares them with a frozen copy).
No UI code.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .midi_io import BAR, PPQ, Note

DATA = Path(__file__).resolve().parent / "data"
PATTERN_DIR = DATA / "patterns"
ACCENTS_FILE = DATA / "accents.json"

SUSTAIN, EIGHTHS, SIXTEENTHS, SIXTEENTHS_ALT, STABS, HALF_TIME = (
    "sustain", "8ths", "16ths", "16ths_alt", "stabs", "half_time")
V1_PATTERNS = (SUSTAIN, EIGHTHS, SIXTEENTHS, SIXTEENTHS_ALT, STABS, HALF_TIME)
V13_PATTERNS = ("arp_up", "arp_down", "arp_updown", "arp_8ths", "arp_rolling", "arp_r5810", "stabs_sync", "stabs_push",
                "hit_downbeat")  # Milestone 8 (v1.3): arpeggios and hits
ACCENT = 0.8  # unaccented notes play at 80% of the part's velocity
EIGHTH, SIXTEENTH = PPQ // 2, PPQ // 4
STAB_HITS = (0, PPQ + EIGHTH)  # beat 1 and the "and" of 2
HALF_HITS = (0, 2 * PPQ)  # beats 1 and 3

# note modes
CHORD_TONES, HYBRID, SCALE_STEPS = "chord", "hybrid", "scale"
NOTE_MODES = (CHORD_TONES, HYBRID, SCALE_STEPS)
NOTE_MODE_NAMES = {CHORD_TONES: "Chord tones", HYBRID: "Hybrid", SCALE_STEPS: "Scale steps"}
PATTERN_ACCENTS = "pattern"  # the accent setting's default: the pattern's own accents
_STEPS = {"8th": EIGHTH, "16th": SIXTEENTH}


class PatternError(ValueError):
    pass


@dataclass(frozen=True)
class Pattern:
    id: str
    name: str
    short: str
    order: int
    family: str
    kind: str
    step: int = EIGHTH  # ticks (grid)
    hits: tuple[int, ...] = ()  # ticks in the bar (hits)
    length: int = EIGHTH  # ticks (hits)
    accents: tuple[int, ...] | None = None  # ticks in the bar; None: every hit accented
    contour: tuple[int, ...] = (0,)
    octaves: tuple[int, ...] = (0,)
    min_step: int = 1
    end_on_anchor: bool = False
    passing: bool = False
    choir: bool = False
    description: str = ""
    note_mode: str | None = None
    degrees: bool = False
    anticipate: bool = False
    down: str | None = None

    @property
    def flat(self) -> bool:
        """Only the anchor (no contour, no octaves)."""
        return not any(self.contour) and not any(self.octaves)


@dataclass(frozen=True)
class Grouping:
    id: str
    name: str
    starts: tuple[int, ...]  # ticks in the bar where a group starts (accented)
    gate: float = 1.0  # length of unaccented notes (fraction)


def _parse_pattern(raw: dict, name: str) -> Pattern:
    try:
        kind = raw["kind"]
        if kind not in ("sustain", "grid", "hits"):
            raise PatternError(f"{name}: kind must be sustain, grid or hits")
        contour = tuple(int(x) for x in raw.get("contour", [0]))
        octaves = tuple(int(x) for x in raw.get("octaves", [0]))
        if not contour or contour[0] != 0 or not octaves or octaves[0] != 0:
            raise PatternError(f"{name}: a pattern's first note must be the part's own note (contour and "
                               "octaves start with 0)")
        accents = raw.get("accents")
        p = Pattern(
            id=str(raw["id"]), name=str(raw["name"]), short=str(raw.get("short", "")), order=int(raw.get("order", 99)),
            family=str(raw.get("family", raw["id"])), kind=kind,
            step=_STEPS[raw.get("step", "8th")],
            hits=tuple(int(h) * SIXTEENTH for h in raw.get("hits", [])),
            length=int(raw.get("length", 2)) * SIXTEENTH,
            accents=None if accents is None else tuple(int(a) * SIXTEENTH for a in accents),
            contour=contour, octaves=octaves, min_step=int(raw.get("min_step", 1)),
            end_on_anchor=bool(raw.get("end_on_anchor", False)), passing=bool(raw.get("passing", False)),
            choir=bool(raw.get("choir", False)), description=str(raw.get("description", "")),
            note_mode=raw.get("note_mode"), degrees=bool(raw.get("degrees", False)),
            anticipate=bool(raw.get("anticipate", False)), down=raw.get("down"))
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, PatternError):
            raise
        raise PatternError(f"{name}: {type(exc).__name__}: {exc}") from None
    if kind == "hits" and (not p.hits or any(not 0 <= h < BAR for h in p.hits) or p.hits[0] != 0):
        raise PatternError(f"{name}: hits are 16th positions 0-15 and start at 0")
    if p.passing and kind != "grid":
        raise PatternError(f"{name}: only grid patterns can end on a passing tone")
    if p.note_mode is not None and p.note_mode not in NOTE_MODES:
        raise PatternError(f"{name}: note_mode must be one of {', '.join(NOTE_MODES)}")
    if p.degrees and any(c not in (0, 3, 5, 8, 10) for c in p.contour):
        raise PatternError(f"{name}: degrees are 0, 3, 5, 8 or 10")
    if p.anticipate and kind != "hits":
        raise PatternError(f"{name}: only hits patterns can anticipate")
    if p.choir and (not p.flat or (kind == "grid" and p.step < EIGHTH)):
        raise PatternError(f"{name}: choirs sing only patterns that repeat their note in 8ths or longer")
    return p


@lru_cache(maxsize=1)
def library() -> dict[str, Pattern]:
    """Every pattern in data/patterns/, in menu order (the v1 patterns first)."""
    out = {}
    for path in sorted(PATTERN_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PatternError(f"{path.name}: not valid JSON ({exc})") from None
        p = _parse_pattern(raw, path.name)
        if p.id in out:
            raise PatternError(f"{path.name}: pattern id {p.id!r} is used twice")
        out[p.id] = p
    missing = set(V1_PATTERNS) - out.keys()
    if missing:
        raise PatternError(f"data/patterns is missing {', '.join(sorted(missing))}")
    for p in out.values():
        if p.down is not None and p.down not in out:
            raise PatternError(f"{p.id}: down pattern {p.down!r} doesn't exist")
    return dict(sorted(out.items(), key=lambda kv: (kv[1].order, kv[0])))


@lru_cache(maxsize=1)
def groupings() -> dict[str, Grouping]:
    raw = json.loads(ACCENTS_FILE.read_text(encoding="utf-8"))
    out = {}
    for g in raw["groupings"]:
        unit = _STEPS[g.get("unit", "16th")]
        starts, t = [], 0
        for n in g["groups"]:
            starts.append(t)
            t += int(n) * unit
        if t != BAR:
            raise PatternError(f"accents.json: grouping {g['id']!r} doesn't fill one 4/4 bar")
        gate = float(g.get("gate", 1.0))
        if not 0 < gate <= 1:
            raise PatternError(f"accents.json: grouping {g['id']!r}: gate must be above 0 and at most 1")
        out[g["id"]] = Grouping(g["id"], g.get("name", g["id"]), tuple(starts), gate)
    return out


PATTERNS = tuple(library())
PATTERN_NAMES = {k: p.name for k, p in library().items()}
PATTERN_SHORT = {k: p.short for k, p in library().items() if p.short}  # grid row tags
CHOIR_PATTERNS = tuple(k for k, p in library().items() if p.choir)  # patterns a choir can sing
PASSING_PATTERNS = tuple(k for k, p in library().items() if p.passing)
ACCENTS = (PATTERN_ACCENTS,) + tuple(groupings())
ACCENT_NAMES = {PATTERN_ACCENTS: "Pattern's own", **{k: g.name for k, g in groupings().items()}}


def allowed(pattern: str, choir: bool) -> bool:
    return pattern in (CHOIR_PATTERNS if choir else PATTERNS)


def family(pattern: str) -> list[str]:
    """The pattern's family (pattern alternatives pick within it), menu order."""
    f = library()[pattern].family
    return [k for k, p in library().items() if p.family == f]


def grid_patterns() -> tuple[str, ...]:
    return tuple(k for k, p in library().items() if p.kind == "grid")


FAMILY_DOWN = {"16ths": "8ths", "arp": "8ths", "8ths": "half_time", "pulse": "sustain", "hit": "sustain"}


def step_down(pattern: str, steps: int, choir: bool = False) -> str:
    """The pattern `steps` levels quieter (intensity shapes): its own `down`, else its family's next pattern
    (16ths -> 8ths -> half-time -> Sustain). A choir only goes to patterns it can sing (else Sustain)."""
    lib = library()
    for _ in range(max(0, steps)):
        p = lib[pattern]
        if p.kind == "sustain":
            break
        pattern = p.down or FAMILY_DOWN.get(p.family, SUSTAIN)
    return pattern if allowed(pattern, choir) else SUSTAIN


def soft(velocity: int, factor: float = ACCENT) -> int:
    return max(1, round(velocity * factor))


def _grid(start: int, end: int, step: int) -> list[tuple[int, int]]:
    out, t = [], start
    while t < end:
        out.append((t, min(t + step, end)))
        t += step
    return out


def _hits(start: int, end: int, offsets: tuple[int, ...], length: int) -> list[tuple[int, int]]:
    """Hits at these offsets in every bar of the span, plus one at the span's start."""
    times = {start}
    bar = start - start % BAR
    while bar < end:
        times.update(bar + o for o in offsets if start <= bar + o < end)
        bar += BAR
    times = sorted(times)
    return [(t, min(t + length, end, nxt)) for t, nxt in zip(times, times[1:] + [end])]


def passing_pitch(pitch: int, nxt: int | None, scale: set[int]) -> int | None:
    """The diatonic step between two notes a 3rd apart (None if there isn't exactly one)."""
    if nxt is None or abs(nxt - pitch) not in (3, 4):
        return None
    lo, hi = sorted((pitch, nxt))
    steps = [p for p in range(lo + 1, hi) if p % 12 in scale]
    return steps[0] if len(steps) == 1 else None


# ---------------------------------------------------------------- note modes
def chord_scale(chord_pcs: set[int], key) -> set[int]:
    """The chord's scale: the key's natural scale with the chord's own tones put in. A chord tone outside the
    scale replaces the scale note it alters, by the key's spelling: a sharp replaces the note below it (G# for
    G in an E major chord in A minor), a flat the note above it (Ab for A in Fm in C major)."""
    out = {(key.tonic_pc + s) % 12 for s in key.steps}
    for c in sorted(chord_pcs):
        if c in out:
            continue
        name = key.pc_name(c)
        nb = (c - 1) % 12 if "#" in name else (c + 1) % 12
        if nb in out and nb not in chord_pcs:
            out.discard(nb)
        out.add(c)
    return out


def step_pitch(anchor: int, k: int, pcs: set[int], min_step: int = 1) -> int | None:
    """The k-th pitch of these pitch classes away from the anchor (up for k > 0, down for k < 0), the first
    at least min_step semitones away. None if there is none within three octaves."""
    if k == 0:
        return anchor
    d = 1 if k > 0 else -1
    found = 0
    for dist in range(min_step, 37):
        q = anchor + d * dist
        if q % 12 in pcs:
            found += 1
            if found == abs(k):
                return q
    return None


def _snap(q: int, chord_pcs: set[int], direction: int) -> int:
    """The nearest chord tone (a tie goes the contour's way)."""
    for dist in range(0, 7):
        ups, downs = q + dist, q - dist
        first, second = (ups, downs) if direction > 0 else (downs, ups)
        if first % 12 in chord_pcs:
            return first
        if second % 12 in chord_pcs:
            return second
    return q


DEGREE_TARGETS = {3: (3, 4, 2, 5), 5: (7, 6, 8, 5), 8: (12,), 10: (15, 16, 14, 17)}


def degree_pitch(anchor: int, degree: int, chord_pcs: set[int]) -> int | None:
    """A chord tone at this degree above the anchor (3rd, 5th, octave, 10th), the interval's usual sizes first."""
    if degree == 0:
        return anchor
    for d in DEGREE_TARGETS[degree]:
        if (anchor + d) % 12 in chord_pcs or d == 12:
            return anchor + d
    return None


def make_mapper(anchor: int, chord_pcs: set[int], scale_pcs: set[int], mode: str, ok, min_step: int = 1,
                degrees: bool = False):
    """mapper(offset, octave, strong) -> pitch for one part at one chord."""
    if mode not in NOTE_MODES:
        raise PatternError(f"unknown note mode {mode!r}")
    cache: dict = {}
    if degrees:  # arpeggio degrees above the anchor; an octave lower if out of range, else the anchor
        def dmapper(off: int, octave: int, strong: bool) -> int:
            if off not in cache:
                q = degree_pitch(anchor, off, chord_pcs)
                cache[off] = next((x for x in (() if q is None else (q, q - 12)) if ok(x)), anchor)
            return cache[off]
        return dmapper

    def resolve(o: int, strong: bool) -> int | None:
        if o == 0:
            return anchor
        if mode == CHORD_TONES:
            return step_pitch(anchor, o, chord_pcs, min_step)
        q = step_pitch(anchor, o, scale_pcs, 1)
        if q is not None and mode == HYBRID and strong and q % 12 not in chord_pcs:
            q = _snap(q, chord_pcs, 1 if o > 0 else -1)
        return q

    def mapper(off: int, octave: int, strong: bool) -> int:
        k = (off, octave, strong and mode == HYBRID)
        if k in cache:
            return cache[k]
        out = anchor
        for o in ((off, -off) if off else (0,)):
            q = resolve(o, strong)
            if q is None:
                continue
            hit = next((q + 12 * oc for oc in ((octave, -octave) if octave else (0,)) if ok(q + 12 * oc)), None)
            if hit is not None:
                out = hit
                break
        cache[k] = out
        return out
    return mapper


# ---------------------------------------------------------------- rendering
def render(pattern: str, pitch: int, start: int, end: int, velocity: int, *, alt: int | None = None,
           passing: int | None = None, mapper=None, grouping: str | None = None, soft_factor: float = ACCENT
           ) -> list[Note]:
    """Notes for one part at one chord.

    mapper(offset, octave, strong) gives the pitch of a contour step (see make_mapper); without one, the
    v1 rule applies: `alt` is the step below for 16ths alternating, every other step is the anchor.
    passing: a passing tone that replaces the last 8th of a passing pattern (moderate mode).
    grouping: an accent grouping id (data/accents.json) instead of a grid pattern's own accents.
    """
    p = library().get(pattern)
    if p is None:
        raise ValueError(f"unknown pattern {pattern!r}")
    if p.kind == "sustain":
        return [Note(pitch, start, end, velocity)]
    if mapper is None:
        def mapper(off, octave, strong, _alt=alt):
            if off == -1 and _alt is not None and not octave:
                return _alt
            return pitch
    gate = 1.0
    accents = p.accents
    if grouping not in (None, PATTERN_ACCENTS) and p.kind == "grid":
        g = groupings()[grouping]
        accents, gate = g.starts, g.gate
    acc = None if accents is None else set(accents)
    cells = _grid(start, end, p.step) if p.kind == "grid" else _hits(start, end, p.hits, p.length)
    last = len(cells) - 1
    notes = []
    nc, no = len(p.contour), len(p.octaves)
    for k, (s, e) in enumerate(cells):
        accented = acc is None or s % BAR in acc
        if k == last and p.end_on_anchor:
            q = pitch
        else:
            off, octave = p.contour[k % nc], p.octaves[k % no]
            q = pitch if not off and not octave else mapper(off, octave, accented or s % PPQ == 0)
        if not accented and gate < 1:
            e = s + max(SIXTEENTH // 2, round((e - s) * gate))
        notes.append(Note(q, s, e, velocity if accented else soft(velocity, soft_factor)))
    if passing is not None and p.passing and len(notes) >= 4:
        # the last 8th of the chord (one 8th or two 16ths) becomes the passing tone
        n_last = max(1, EIGHTH // p.step)
        notes = notes[:-n_last] + [Note(passing, n.start, n.end, soft(velocity, soft_factor))
                                   for n in notes[-n_last:]]
    return notes


def split_at_bars(notes: list[Note]) -> list[Note]:
    """Re-strike every bar: a note that crosses a bar line is cut there and struck again."""
    out = []
    for n in notes:
        s = n.start
        while True:
            nxt = (s // BAR + 1) * BAR
            if nxt >= n.end:
                out.append(Note(n.pitch, s, n.end, n.velocity))
                break
            out.append(Note(n.pitch, s, nxt, n.velocity))
            s = nxt
    return out
