"""Generator (SPEC §5): safe mode, three approaches (A low and warm, B wide and full, C high and bright).

How it works
    1. Lines. One master list of instrument lines (`LINES`, score order; divisi lines are separate lines).
       Each line carries an abstract *voice*:
          B   the bass (the chord's bass note: root or slash bass), doubled in octaves
          L5  an open 5th above the bass, for root-position chords that have a perfect 5th
          h1-h4  four upper harmony voices, low to high
       The ensemble (preset instruments, the Forces and Density sliders) picks which lines exist; the
       approach sets each line's voice, octave offsets and whether it plays. Per voice, the first line in
       priority order (strings > brass > woodwinds > choir, then the approach's lead order) is the primary;
       every other line on that voice doubles it. Bass and L5 lines move together on purpose (group "low").
    2. Candidates. For each chord, every voicing of the bass and upper voices from the labelled chord tones
       (safe mode) is built, cheap rules prune it, and it is scored by the approach (register, span,
       doubling, horns in their heroic zone, optionally the input's top note). Each surviving candidate is
       run through the real rule checker on its own, together with any fixed parts (locked parts and the
       kept input voicing).
    3. Path. A seeded Viterbi search picks one candidate per chord with the lowest total of chord scores
       plus voice-leading costs. Choir leaps over an octave and choir parallels are never allowed.
    4. Notes. Every part sustains for the chord's length; a note common to two consecutive identical chords
       is tied through.
    5. Check. The whole result is checked. It is returned only with no errors and no `generator_must_pass`
       warnings except those that come only from fixed parts (your locked parts or kept voicing, which are
       shown flagged); otherwise GenerationError is raised.

The same chords, key, settings and seed always give the same result. Approach A at the default settings
gives exactly the Milestone 3 result (tests/data/a_v03_snapshot.json).
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field, replace

from .analysis.chords import QUALITIES, ChordLabel
from .checker import ChordSpan, Part, Report, check, required_tones
from .instruments import SECTIONS, Instrument, instruments as builtin_instruments
from .midi_io import Note, position_text
from .rules import SAFE, Rules, rules as builtin_rules
from .theory import Key

VOICES = ("B", "L5", "h1", "h2", "h3", "h4")
UPPER = ("h1", "h2", "h3", "h4")
SECTION_PRIORITY = ("strings", "brass", "woodwinds", "choir")  # which section's line is the primary
APPROACHES = ("A", "B", "C")

# Dynamics slider (SPEC §6): velocity and one constant CC1 value per part.
DYNAMICS = {"pp": 30, "p": 50, "mp": 65, "mf": 80, "f": 100, "ff": 120}
DYNAMIC_STEPS = tuple(DYNAMICS)
VELOCITY = 80  # mf, the default
CC1 = 80
FORCES = ("solo", "section", "divisi")
DENSITY_STEPS = (1, 2, 3, 4, 5)
TOP_SMOOTH, TOP_INPUT = "smooth", "input"

# Search sizes. KEEP valid candidates per chord go into the path search; more if no path is found.
KEEP = (40, 200)
MAX_CANDIDATES_CHECKED = 2500

BASS_WINDOW = (40, 51)  # the bass voice: E2..Eb3, one octave so octave doublings stay fixed
HEROIC = (53, 65)  # horn F3..F4
PARALLEL_COST = 8.0  # parallel 5ths/8ves between independent lines (a checker warning): avoided when possible
SAME_AS_BEFORE_COST = 2.0  # "Regenerate" pushes away from the previous result
KEEP_GROUP = "keep"


class GenerationError(Exception):
    """No orchestration passes the rules. The message is shown to the user."""


@dataclass(frozen=True)
class Line:
    id: str  # part id, e.g. "vln1-a"
    instrument: str
    label: str  # display name, e.g. "Violins I a"
    export: str  # file-name part, e.g. "Vln1-a"
    voices: tuple[str, ...]  # voices this line can carry, in order of preference
    octaves: tuple[int, ...] = (0,)  # octave offsets tried in order (must stay in comfortable range)
    role: str = "mid_harmony"
    forces: tuple[str, ...] = ("section", "divisi")  # Forces slider positions this line exists in
    program: int | None = None  # audition GM program, if not the instrument's


_ALL = ("solo", "section", "divisi")
_SEC = ("section",)
_DIV = ("divisi",)
_SOLO = ("solo",)

# The master line list, in score order. The first block is Milestone 3's approach A, unchanged.
LINES: tuple[Line, ...] = (
    Line("picc", "piccolo", "Piccolo", "Picc", ("h4",), (12, 24), role="high_harmony", forces=_ALL),
    Line("fl1", "flute", "Flute 1", "Fl1", ("h4",), role="high_harmony", forces=_ALL),
    Line("fl2", "flute", "Flute 2", "Fl2", ("h3",), role="high_harmony"),
    Line("ob1", "oboe", "Oboe 1", "Ob1", ("h4",), role="high_harmony", forces=_ALL),
    Line("ob2", "oboe", "Oboe 2", "Ob2", ("h3",), role="high_harmony"),
    Line("eh", "english_horn", "English horn", "EH", ("h2",), forces=_ALL),
    Line("cl1", "clarinet", "Clarinet 1", "Cl1", ("h3",), role="high_harmony", forces=_ALL),
    Line("cl2", "clarinet", "Clarinet 2", "Cl2", ("h2",)),
    Line("bcl", "bass_clarinet", "Bass clarinet", "BCl", ("h1",), role="low_harmony", forces=_ALL),
    Line("bn1", "bassoon", "Bassoon 1", "Bn1", ("L5",), role="low_harmony"),
    Line("bn2", "bassoon", "Bassoon 2", "Bn2", ("B",), (0, 12), role="bass", forces=_ALL),
    Line("cbn", "contrabassoon", "Contrabassoon", "Cbn", ("B",), (-12, 0), role="bass", forces=_ALL),
    Line("hn1", "horn", "Horn 1", "Hn1", ("h4",), role="high_harmony"),
    Line("hn2", "horn", "Horn 2", "Hn2", ("h3",), role="high_harmony"),
    Line("hn3", "horn", "Horn 3", "Hn3", ("h2",), forces=_ALL),
    Line("hn4", "horn", "Horn 4", "Hn4", ("h1",), role="low_harmony"),
    Line("tpt1", "trumpet", "Trumpet 1", "Tpt1", ("h4",), role="high_harmony", forces=_ALL),
    Line("tpt2", "trumpet", "Trumpet 2", "Tpt2", ("h3",), role="high_harmony"),
    Line("tpt3", "trumpet", "Trumpet 3", "Tpt3", ("h2",)),
    Line("tbn1", "tenor_trombone", "Trombone 1", "Tbn1", ("h1",), role="low_harmony", forces=_ALL),
    Line("tbn2", "tenor_trombone", "Trombone 2", "Tbn2", ("L5",), role="low_harmony"),
    Line("btbn", "bass_trombone", "Bass trombone", "BTbn", ("B",), role="bass", forces=_ALL),
    Line("tba", "tuba", "Tuba", "Tba", ("B",), (-12, 0), role="bass", forces=_ALL),
    # strings: solo players, sections, and extra divisi lines
    Line("vln1-solo", "violins_1", "Violin I solo", "Vln1-solo", ("h4",), role="high_harmony", forces=_SOLO,
         program=40),
    Line("vln1-a", "violins_1", "Violins I a", "Vln1-a", ("h4",), role="high_harmony"),
    Line("vln1-b", "violins_1", "Violins I b", "Vln1-b", ("h3",), role="high_harmony"),
    Line("vln2-solo", "violins_2", "Violin II solo", "Vln2-solo", ("h3",), role="high_harmony", forces=_SOLO,
         program=40),
    Line("vln2", "violins_2", "Violins II", "Vln2", ("h2",), forces=_SEC),
    Line("vln2-a", "violins_2", "Violins II a", "Vln2-a", ("h3",), role="high_harmony", forces=_DIV),
    Line("vln2-b", "violins_2", "Violins II b", "Vln2-b", ("h2",), forces=_DIV),
    Line("vla-solo", "violas", "Viola solo", "Vla-solo", ("h1",), role="low_harmony", forces=_SOLO, program=41),
    Line("vla", "violas", "Violas", "Vla", ("h1",), role="low_harmony", forces=_SEC),
    Line("vla-a", "violas", "Violas a", "Vla-a", ("h2",), forces=_DIV),
    Line("vla-b", "violas", "Violas b", "Vla-b", ("h1",), role="low_harmony", forces=_DIV),
    Line("vc-solo", "cellos", "Cello solo", "Vc-solo", ("B",), role="bass", forces=_SOLO, program=42),
    Line("vc", "cellos", "Cellos", "Vc", ("B",), role="bass", forces=_SEC),
    Line("vc-a", "cellos", "Cellos a", "Vc-a", ("B",), role="bass", forces=_DIV),
    Line("vc-b", "cellos", "Cellos b", "Vc-b", ("L5",), role="low_harmony", forces=_DIV),
    Line("cb-solo", "basses", "Bass solo", "Cb-solo", ("B",), (-12, 0), role="bass", forces=_SOLO, program=43),
    Line("cb", "basses", "Basses", "Cb", ("B",), (-12, 0), role="bass", forces=("section", "divisi")),
    Line("ch-s", "choir_soprano", "Choir soprano", "ChS", ("h4",), role="high_harmony", forces=_ALL),
    Line("ch-a", "choir_alto", "Choir alto", "ChA", ("h3",), forces=_ALL),
    Line("ch-t", "choir_tenor", "Choir tenor", "ChT", ("h2",), forces=_ALL),
    Line("ch-b", "choir_bass", "Choir bass", "ChB", ("B",), role="bass", forces=_ALL),  # octave chosen per chord
)
LINE_BY_ID = {ln.id: ln for ln in LINES}
LINES_A = tuple(ln for ln in LINES if ln.id not in ("picc", "tpt3") and "section" in ln.forces)  # M3 list
CHOIR_BASS = "ch-b"
CHOIR_IDS = ("ch-s", "ch-a", "ch-t", CHOIR_BASS)
CHOIR_INSTRUMENTS = {"ch-s": "choir_soprano", "ch-a": "choir_alto", "ch-t": "choir_tenor", "ch-b": "choir_bass"}

# Keep-as-is: string lines that can take the input voicing, low to high, each with a home pitch.
KEEP_SLOTS: tuple[tuple[str, str, str, str, int], ...] = (
    # id, instrument, label, export, home pitch (MIDI)
    ("k-cb", "basses", "Basses (as written)", "Cb", 36),
    ("k-cb-b", "basses", "Basses b (as written)", "Cb-b", 43),
    ("k-vc-a", "cellos", "Cellos a (as written)", "Vc-a", 45),
    ("k-vc-b", "cellos", "Cellos b (as written)", "Vc-b", 52),
    ("k-vc-c", "cellos", "Cellos c (as written)", "Vc-c", 57),
    ("k-vla-a", "violas", "Violas a (as written)", "Vla-a", 55),
    ("k-vla-b", "violas", "Violas b (as written)", "Vla-b", 60),
    ("k-vla-c", "violas", "Violas c (as written)", "Vla-c", 64),
    ("k-vln2-a", "violins_2", "Violins II a (as written)", "Vln2-a", 64),
    ("k-vln2-b", "violins_2", "Violins II b (as written)", "Vln2-b", 67),
    ("k-vln2-c", "violins_2", "Violins II c (as written)", "Vln2-c", 71),
    ("k-vln1-a", "violins_1", "Violins I a (as written)", "Vln1-a", 72),
    ("k-vln1-b", "violins_1", "Violins I b (as written)", "Vln1-b", 76),
    ("k-vln1-c", "violins_1", "Violins I c (as written)", "Vln1-c", 79),
)
KEEP_LINES = tuple(Line(i, inst, label, exp, (), role="bass" if n == 0 else "mid_harmony", forces=_ALL)
                   for n, (i, inst, label, exp, _) in enumerate(KEEP_SLOTS))
KEEP_LINE_BY_ID = {ln.id: ln for ln in KEEP_LINES}


@dataclass(frozen=True)
class Approach:
    id: str
    name: str
    upper_window: tuple[int, int]  # pitch window of the upper voices
    center: float  # target mean of the upper voices
    span: int  # upper voices within about this many semitones
    bass: tuple[int, int]  # preferred bass-voice pitches
    min_span: int = 0  # wide approaches: upper voices at least this wide
    top_pull: float = 0.0  # pull the top voice upward (bright)
    lines: dict = field(default_factory=dict)  # line id -> None (rests) or (voices, octaves)
    parallel_cost: float = PARALLEL_COST
    lead: tuple[str, ...] = ()  # density order (most important first); unlisted lines follow in score order


A = Approach(
    "A", "Low and warm", (48, 77), 60.0, 14, (40, 47),
    lines={"picc": None, "tpt3": None,
           # divisi: Violins II and violas split, cellos add the open 5th
           },
    lead=("vln1-a", "vln1-solo", "vc", "vc-a", "vc-solo", "hn1", "hn2", "hn3", "hn4", "vla", "vla-b", "vla-solo",
          "vln2", "vln2-b", "vln2-solo", "vln1-b", "vln2-a", "vla-a", "cb", "cb-solo", "tbn2", "tbn1", "btbn",
          "tba", "vc-b", "bn1", "bn2", "ch-s", "ch-a", "ch-t", "ch-b", "cl1", "cl2", "bcl", "eh", "cbn", "ob1",
          "ob2", "fl1", "fl2", "tpt1", "tpt2"),
)
B = Approach(
    "B", "Wide and full", (48, 79), 63.0, 26, (40, 44), min_span=17, parallel_cost=16.0,
    lines={"picc": (("h4",), (24, 12)), "fl1": (("h4",), (12, 0)), "fl2": (("h3",), (12, 0)),
           "ob1": (("h4",), (0, 12)), "cl1": (("h3",), (0, 12)),
           "vln1-a": (("h4",), (12, 0)), "vln1-b": (("h4",), (0,)), "vln1-solo": (("h4",), (12, 0)),
           "vln2": (("h3",), (0,)), "vla": (("h2",), (0,)), "vln2-a": (("h4",), (0,)), "vln2-b": (("h3",), (0,)),
           "vla-a": (("h2",), (0,)), "vla-b": (("h1",), (0,)),
           "cb": (("B",), (-12,)), "cbn": (("B",), (-12,)), "tba": (("B",), (-12, 0)),
           "tpt3": None},
    lead=("vln1-a", "vln1-solo", "vc", "vc-a", "vc-solo", "cb", "cb-solo", "vln1-b", "vln2", "vla", "vln2-solo",
          "vla-solo", "vln2-a", "vln2-b", "vla-a", "vla-b", "hn1", "hn2", "hn3", "hn4", "tba", "tbn1", "tbn2",
          "btbn", "ch-s", "ch-a", "ch-t", "ch-b", "fl1", "picc", "tpt1", "tpt2", "ob1", "cl1", "bn2", "cbn",
          "fl2", "ob2", "cl2", "eh", "bcl", "bn1", "vc-b"),
)
C = Approach(
    "C", "High and bright", (55, 84), 70.0, 14, (45, 51), top_pull=0.1, parallel_cost=16.0,
    lines={"picc": (("h4",), (12, 24)), "fl1": (("h4",), (12, 0)), "fl2": (("h4",), (0,)),
           "ob1": (("h4",), (0,)), "ob2": (("h3",), (0,)), "cl1": (("h3",), (0,)), "cl2": (("h2",), (0,)),
           "bcl": None, "bn1": None, "cbn": None, "tbn2": None, "tba": None, "vc-b": None,
           "hn1": (("h3",), (0,)), "hn2": (("h2",), (0,)), "hn3": (("h1",), (0,)), "hn4": None,
           "tpt1": (("h4",), (0,)), "tpt2": (("h3",), (0,)), "tpt3": (("h2",), (0,)),
           "vln1-a": (("h4",), (12, 0)), "vln1-b": (("h4",), (0,)), "vln1-solo": (("h4",), (0,)),
           "vln2": (("h3",), (0,)), "vla": (("h2",), (0,)), "vln2-a": (("h3",), (0,)), "vln2-b": (("h2",), (0,)),
           "vla-a": (("h2",), (0,)), "vla-b": (("h1",), (0,)), "vla-solo": (("h2",), (0,)),
           "vln2-solo": (("h3",), (0,)),
           "cb": (("B",), (0, -12)), "cb-solo": (("B",), (0, -12))},
    lead=("vln1-a", "vln1-solo", "vln1-b", "vln2", "vln2-a", "vln2-solo", "vla", "vla-a", "vla-solo", "vc",
          "vc-a", "vc-solo", "fl1", "picc", "tpt1", "ob1", "tpt2", "tpt3", "fl2", "ob2", "cl1", "cl2", "vln2-b",
          "vla-b", "cb", "cb-solo", "hn1", "hn2", "hn3", "eh", "ch-s", "ch-a", "ch-t", "ch-b", "bn2", "tbn1",
          "btbn"),
)
APPROACH = {"A": A, "B": B, "C": C}


@dataclass(frozen=True)
class Ensemble:
    """Which instruments play, plus the Forces and Density sliders.

    `Ensemble(sections)` turns whole sections on (Milestone 3 toggles); presets pass `instruments`.
    """
    sections: frozenset[str] = frozenset(SECTIONS)
    instruments: frozenset[str] | None = None
    forces: str = "section"
    density: int = 5

    def __post_init__(self):
        bad = set(self.sections) - set(SECTIONS)
        if bad:
            raise ValueError(f"unknown section(s) {sorted(bad)}")
        if self.forces not in FORCES:
            raise ValueError(f"forces must be one of {FORCES}")
        if self.density not in DENSITY_STEPS:
            raise ValueError("density must be 1-5")
        if self.instruments is not None:
            object.__setattr__(self, "instruments", frozenset(self.instruments))
            if not self.instruments:
                raise ValueError("at least one instrument must play")
        elif not self.sections:
            raise ValueError("at least one section must play")

    def active(self, insts: dict[str, Instrument]) -> frozenset[str]:
        if self.instruments is not None:
            unknown = self.instruments - set(insts)
            if unknown:
                raise ValueError(f"unknown instrument(s) {sorted(unknown)}")
            return self.instruments
        return frozenset(i for i, inst in insts.items() if inst.section in self.sections)


@dataclass(frozen=True)
class Settings:
    """Everything besides chords, key and seed that shapes a generation."""
    ensemble: Ensemble = Ensemble()
    top_voice: str = TOP_SMOOTH  # "smooth" or "input"
    tops: tuple[int | None, ...] = ()  # the input clip's top note per chord (for "input")
    keep: tuple[tuple[int, ...], ...] | None = None  # the input voicing per chord, kept in the strings
    dynamics: str = "mf"

    @property
    def velocity(self) -> int:
        return DYNAMICS[self.dynamics]


@dataclass(frozen=True)
class _Cand:
    """One chord's voicing: abstract voices plus the actual pitch of every model line (None = rests)."""
    voices: tuple[tuple[str, int], ...]  # (voice, pitch) for sounding voices
    pitches: tuple[tuple[str, int | None], ...]  # (line id, pitch) for every model line
    cost: float

    def __post_init__(self):  # lookup tables (the search reads these millions of times)
        object.__setattr__(self, "vd", dict(self.voices))
        object.__setattr__(self, "pd", dict(self.pitches))
        object.__setattr__(self, "ch", {lid: self.pd[lid] for lid in CHOIR_IDS if self.pd.get(lid) is not None})

    def v(self, name: str) -> int | None:
        return self.vd.get(name)

    def p(self, line_id: str) -> int | None:
        return self.pd.get(line_id)

    @property
    def key(self):
        return self.pitches


@dataclass
class Orchestration:
    """A finished, checked orchestration (one alternative). Treat it as immutable: edits make new ones."""
    approach: str
    reason: str
    key: Key
    mode: str
    seed: int
    chords: list[ChordSpan]
    lines: list[Line]  # every line of the ensemble, score order (some may rest throughout)
    parts: list[Part]  # same order as lines
    cells: dict[str, list[int | None]]  # line id -> pitch per chord (None = rest)
    report: Report
    velocity: int = VELOCITY
    cc1: int = CC1
    meta: dict = field(default_factory=dict)
    # meta: "voices" (abstract voicing per chord), "labels" (line id -> voice label per chord),
    # "settings", "variation", "sources" (approach letter per chord), "fixed" (ids of fixed lines)

    def part(self, line_id: str) -> Part:
        return next(p for p in self.parts if p.id == line_id)

    def line(self, line_id: str) -> Line:
        return next(ln for ln in self.lines if ln.id == line_id)

    @property
    def sounding_lines(self) -> list[Line]:
        return [ln for ln in self.lines if any(p is not None for p in self.cells[ln.id])]

    @property
    def settings(self) -> Settings:
        return self.meta.get("settings", Settings())

    @property
    def sources(self) -> list[str]:
        return self.meta.get("sources", [self.approach] * len(self.chords))


# ---------------------------------------------------------------- ensemble -> lines
def ensemble_lines(ensemble: Ensemble, insts: dict[str, Instrument], keep: bool = False) -> list[Line]:
    """Every line the ensemble can use (any approach), score order. Keep-as-is swaps the strings for slots."""
    active = ensemble.active(insts)
    out = [ln for ln in LINES if ln.instrument in active and ensemble.forces in ln.forces]
    if keep:
        out = [ln for ln in out if insts[ln.instrument].section != "strings"]
        out += list(KEEP_LINES)
    return out


def _priority(line: Line, insts, approach: Approach) -> tuple:
    rank = {s: i for i, s in enumerate(SECTION_PRIORITY)}
    order = {ln.id: i for i, ln in enumerate(LINES)}
    return rank[insts[line.instrument].section], order.get(line.id, 999)


def approach_lines(approach: Approach, ensemble: Ensemble, insts: dict[str, Instrument],
                   exclude: set[str] = frozenset(), keep: bool = False) -> list[Line]:
    """The model lines this approach plays for the ensemble, with the approach's voices and octaves,
    after the Density slider (most important lines per voice first; the choir plays as a whole)."""
    lines = []
    for ln in ensemble_lines(ensemble, insts, keep):
        if ln.id in exclude or ln.id in KEEP_LINE_BY_ID:
            continue
        spec = approach.lines.get(ln.id, (ln.voices, ln.octaves))
        if spec is None:
            continue
        lines.append(replace(ln, voices=spec[0], octaves=spec[1]))
    lines = _spread_upper(lines, insts)
    if ensemble.density < 5:
        lines = _thin(lines, approach, insts, {1: 1, 2: 2, 3: 3, 4: 5}[ensemble.density])
    return _anchor_octaves(lines, insts)


def _thin(lines: list[Line], approach: Approach, insts, k: int) -> list[Line]:
    """Density: keep the k most important lines per voice (approach lead order). The choir plays as a
    whole, and each section keeps its voices contiguous (no gaps over an octave inside a section)."""
    lead = {lid: i for i, lid in enumerate(approach.lead)}
    score = {ln.id: i for i, ln in enumerate(LINES)}

    def importance(ln):
        return lead.get(ln.id, 100 + score.get(ln.id, 0))

    keepers: set[str] = set()
    for v in VOICES:
        carriers = sorted((ln for ln in lines if ln.voices[0] == v), key=importance)
        keepers.update(ln.id for ln in carriers[:k])
    if any(ln.id in keepers for ln in lines if ln.id in CHOIR_IDS):
        keepers.update(ln.id for ln in lines if ln.id in CHOIR_IDS)
    for sec in SECTIONS:
        mine = [ln for ln in lines if insts[ln.instrument].section == sec and ln.voices[0] in UPPER]
        kept = [UPPER.index(ln.voices[0]) for ln in mine if ln.id in keepers]
        if not kept:
            continue
        for vi in range(min(kept), max(kept) + 1):
            if not any(ln.id in keepers and ln.voices[0] == UPPER[vi] for ln in mine):
                fill = sorted((ln for ln in mine if ln.voices[0] == UPPER[vi]), key=importance)
                if fill:
                    keepers.add(fill[0].id)
    return [ln for ln in lines if ln.id in keepers]


def _anchor_octaves(lines: list[Line], insts) -> list[Line]:
    """A line written an octave (or two) above its voice needs a line of its own section on that voice no
    more than an octave below it; otherwise it moves down until it has one (or plays at the unison), so a
    section never has a gap over an octave. Lines are settled from the lowest offset up."""
    out = {ln.id: ln for ln in lines}
    todo = sorted((ln for ln in lines if ln.voices and ln.voices[0] in UPPER),
                  key=lambda ln: (ln.octaves[0], insts[ln.instrument].comfortable[0]))
    settled: list[Line] = []
    for ln in todo:
        o = ln.octaves[0]
        if o > 0:
            sec = insts[ln.instrument].section
            below = [m.octaves[0] for m in settled
                     if insts[m.instrument].section == sec and m.voices[0] == ln.voices[0] and m.octaves[0] < o]
            top = max(below) + 12 if below else 0
            if o > top:
                kept = tuple(x for x in ln.octaves if x <= top) or (top,)
                ln = replace(ln, octaves=kept)
                out[ln.id] = ln
        settled.append(ln)
    return [out[ln.id] for ln in lines]


def _spread_upper(lines: list[Line], insts: dict[str, Instrument]) -> list[Line]:
    """Small ensembles: when the upper lines cover fewer upper voices than they could (e.g. Low and heavy:
    violas, trombone 1 and choir tenor on two voices), spread them over three voices by register so chords
    with four tones still fit. Ensembles that already have three upper voices are left unchanged."""
    ups = [ln for ln in lines if ln.voices and ln.voices[0] in UPPER]
    target = min(3, len(ups))  # three upper voices + the bass hold any four-tone chord
    if len({ln.voices[0] for ln in ups}) >= target:
        return lines
    order = {ln.id: i for i, ln in enumerate(lines)}

    def reg(ln):
        lo, hi = insts[ln.instrument].comfortable
        return ((lo + hi) / 2, UPPER.index(ln.voices[0]), order[ln.id])

    ranked = sorted(ups, key=reg)
    new = {}
    for k, ln in enumerate(ranked):  # split the ranked lines into `target` groups, low to high
        new[ln.id] = UPPER[k * target // len(ranked)]
    return [replace(ln, voices=(new[ln.id],) + tuple(v for v in ln.voices[1:] if v != new[ln.id]))
            if ln.id in new else ln for ln in lines]


# ---------------------------------------------------------------- setup
class _Setup:
    def __init__(self, lines: list[Line], insts: dict[str, Instrument], approach: Approach,
                 need_bass: bool = True):
        self.inst = insts
        self.approach = approach
        self.lines = lines
        self.choir = any(ln.id == CHOIR_BASS for ln in self.lines)
        rank = {s: i for i, s in enumerate(SECTION_PRIORITY)}
        order = {ln.id: i for i, ln in enumerate(self.lines)}
        lead = {lid: i for i, lid in enumerate(approach.lead)} if approach.id != "A" else order
        self.primary: dict[str, str] = {}
        for v in VOICES:
            carriers = [ln for ln in self.lines if ln.voices[0] == v]
            if carriers:
                best = min(carriers, key=lambda ln: (rank[insts[ln.instrument].section],
                                                     lead.get(ln.id, 100 + order[ln.id])))
                self.primary[v] = best.id
        self.upper = [v for v in UPPER if v in self.primary or any(v in ln.voices for ln in self.lines)]
        self.low_ids = [ln.id for ln in self.lines if ln.voices[0] in ("B", "L5")]
        # upper lines that may switch octave between chords (their motion can differ from the voice's)
        self.switch_ids = [(ln.id, ln.voices[0]) for ln in self.lines
                           if ln.voices[0] in UPPER and len(ln.octaves) > 1]
        self.choir_lines = {ln.voices[0]: ln.id for ln in self.lines if ln.id in CHOIR_IDS}
        if need_bass and "B" not in self.primary:
            raise GenerationError("Nothing can play the bass line with these instruments.")

    def comfortable(self, line: Line, pitch: int) -> bool:
        return self.inst[line.instrument].is_comfortable(pitch)

    def line_pitch(self, line: Line, voices: dict[str, int]) -> int | None:
        for v in line.voices:
            if v in voices:
                for off in line.octaves:
                    p = voices[v] + off
                    if self.comfortable(line, p):
                        return p
                return None  # its preferred sounding voice doesn't fit: rest
        return None


# ---------------------------------------------------------------- candidates
def _sensitive_pcs(label: ChordLabel, key: Key) -> set[int]:
    ivs = QUALITIES[label.quality][0]
    out = {(label.root + 9) % 12} if label.quality == "dim7" else {(label.root + i) % 12 for i in ivs if i in (10, 11)}
    lt = (key.tonic_pc + 11) % 12
    if lt in label.pcs():
        out.add(lt)
    return out


def _vertical_cost(setup: _Setup, label: ChordLabel, voices: dict[str, int], pitches: dict[str, int | None],
                   rng: random.Random, top: int | None = None) -> float:
    ap = setup.approach
    ups = [voices[v] for v in UPPER if v in voices]
    cost = 0.0
    if ups:
        cost += 0.15 * abs(sum(ups) / len(ups) - ap.center)
        cost += 0.25 * max(0, max(ups) - min(ups) - ap.span)
        for a, b in zip(ups, ups[1:]):
            cost += 0.3 * max(0, b - a - 7) + (1.0 if a == b else 0.0)
    b = voices["B"]
    cost += 0.2 * max(0, ap.bass[0] - b, b - ap.bass[1])
    # doubling: root doubled is best; a missing omittable 5th costs a little
    ivs = QUALITIES[label.quality][0]
    pcs = [p % 12 for p in ups]
    if 7 in ivs and (label.root + 7) % 12 not in pcs and "L5" not in voices:
        cost += 0.8
    third = [(label.root + i) % 12 for i in ivs if i in (3, 4)]
    if third and pcs.count(third[0]) > 1:
        cost += 0.6
    if pcs.count(label.root) >= 1:
        cost -= 0.2
    # horns in their heroic zone
    for lid, p in pitches.items():
        if p is not None and lid.startswith("hn") and HEROIC[0] <= p <= HEROIC[1]:
            cost -= 0.15
    # approach B: at least a wide span; approach C: a high top voice
    if ups and ap.min_span:
        cost += 0.25 * max(0, ap.min_span - (max(ups) - min(ups)))
    if ups and ap.top_pull:
        cost -= ap.top_pull * (max(ups) - ap.center)
    if top is not None and ups:
        cost += 0.3 * abs(max(ups) - top)
    return cost + rng.random() * 0.25


def _input_top(setup: _Setup, label: ChordLabel, top: int | None) -> tuple[int | None, int | None]:
    """Follow input: the pitch class the top voice must take, and the octave to aim for (or None, None)."""
    if top is None or top % 12 not in label.pcs():
        return None, None
    lo, hi = setup.approach.upper_window
    target = top
    while target > hi:
        target -= 12
    while target < lo:
        target += 12
    return top % 12, target


def _candidates(setup: _Setup, span: ChordSpan, key: Key, seed, index: int, *, top: int | None = None,
                fixed_pcs: frozenset[int] = frozenset(), avoid: dict[str, int | None] | None = None
                ) -> list[_Cand]:
    label = span.label
    chord_pcs = label.pcs()
    sens = _sensitive_pcs(label, key)
    need = set(required_tones(label)) - set(fixed_pcs)
    ivs = QUALITIES[label.quality][0]
    root_pos = label.bass == label.root
    want_l5 = root_pos and 7 in ivs and any("L5" in ln.voices for ln in setup.lines)
    rng = random.Random(f"{seed}:{index}:{label.root}:{label.quality}:{label.bass}")
    lo, hi = setup.approach.upper_window
    tones = [p for p in range(lo, hi + 1) if p % 12 in chord_pcs]
    n_up = len(setup.upper)
    top_pc, top_target = _input_top(setup, label, top)
    choir_ranges = {}
    for v, lid in setup.choir_lines.items():
        if v != "B" and v in setup.upper:
            choir_ranges[v] = setup.inst[CHOIR_INSTRUMENTS[lid]].comfortable
    out: list[_Cand] = []
    seen = set()
    for bass in range(BASS_WINDOW[0], BASS_WINDOW[1] + 1):
        if bass % 12 != label.bass:
            continue
        for ups in itertools.combinations_with_replacement(tones, n_up):
            # adjacent upper voices: at most an octave apart; unisons allowed (needed e.g. for a choir
            # on power chords) but never three voices on one note
            if any(b - a > 12 for a, b in zip(ups, ups[1:])):
                continue
            if any(a == c for a, c in zip(ups, ups[2:])):
                continue
            if ups and ups[0] <= bass:
                continue
            if top_pc is not None and ups and ups[-1] % 12 != top_pc:
                continue
            voices = {"B": bass}
            for v, p in zip(setup.upper, ups):
                voices[v] = p
            if want_l5 and (not ups or bass + 7 < ups[0]):
                voices["L5"] = bass + 7
            # leading tone / chord 7th in at most one line family (bass + L5 count as one)
            up_pcs = [p % 12 for p in ups]
            low_pcs = {label.bass} | ({(bass + 7) % 12} if "L5" in voices else set())
            if any(up_pcs.count(pc) + (pc in low_pcs) > 1 for pc in sens):
                continue
            if not need <= set(up_pcs) | low_pcs:
                continue
            if any(not (r[0] <= voices[v] <= r[1]) for v, r in choir_ranges.items()):
                continue
            pitches: dict[str, int | None] = {ln.id: (None if ln.id == CHOIR_BASS else setup.line_pitch(ln, voices))
                                              for ln in setup.lines}
            # every voice's primary line must sound it (the choir bass is placed below)
            if any(pitches.get(setup.primary[v]) is None for v in voices
                   if v in setup.primary and setup.primary[v] != CHOIR_BASS):
                continue
            bass_opts = [None]
            if setup.choir:
                tenor = voices.get(next((v for v, lid in setup.choir_lines.items() if lid == "ch-t"), "-"), 127)
                r = setup.inst["choir_bass"].comfortable
                bass_opts = [p for p in range(r[0], r[1] + 1) if p % 12 == label.bass and p <= tenor]
                if not bass_opts:
                    continue
            for cb in bass_opts:
                if cb is not None:
                    pitches = dict(pitches, **{CHOIR_BASS: cb})
                key_ = tuple(sorted(pitches.items()))
                if key_ in seen:
                    continue
                seen.add(key_)
                cost = _vertical_cost(setup, label, voices, pitches, rng, top_target)
                if avoid is not None and all(pitches.get(k) == p for k, p in avoid.items()):
                    cost += SAME_AS_BEFORE_COST
                out.append(_Cand(tuple(sorted(voices.items())), tuple(pitches.items()), cost))
    out.sort(key=lambda c: c.cost)
    return out


# ---------------------------------------------------------------- parts
def _ties(spans: list[ChordSpan]) -> list[bool]:
    """tie[i]: chord i+1 repeats chord i (common notes are held)."""
    return [spans[i].label == spans[i + 1].label and spans[i].end == spans[i + 1].start
            for i in range(len(spans) - 1)]


def build_parts(lines: list[Line], spans: list[ChordSpan], cells: dict[str, list[int | None]],
                labels: dict[str, list[str | None]], velocity: int, insts: dict[str, Instrument],
                tie: list[bool] | None = None) -> list[Part]:
    """Checker parts from per-chord pitches and voice labels.

    A line doubles another when, at every chord where it sounds, the other sounds the same voice label on
    the same pitch class. The other line is searched among lines that sound at least as often, in priority
    order (strings > brass > woodwinds > choir, then score order), so links never form a loop.
    Lines whose voices are all B/L5 form the group "low"; kept input lines form the group "keep".
    """
    tie = _ties(spans) if tie is None else tie
    rank = {s: i for i, s in enumerate(SECTION_PRIORITY)}
    order = {ln.id: i for i, ln in enumerate(lines)}
    count = {ln.id: sum(p is not None for p in cells[ln.id]) for ln in lines}
    # search order: lines that sound most first (a voice's primary always sounds), then priority
    prio = sorted(lines, key=lambda ln: (-count[ln.id], rank[insts[ln.instrument].section], order[ln.id]))
    pos = {ln.id: i for i, ln in enumerate(prio)}
    base = {ln.id: (ln.voices[0] if ln.voices else None) for ln in lines}
    # per chord: whom each sounding line doubles there (first line in priority with the same label and pc)
    by_rank = sorted(lines, key=lambda ln: (rank[insts[ln.instrument].section], order[ln.id]))
    local: dict[str, list[str | None]] = {ln.id: [None] * len(spans) for ln in lines}
    if len(spans) > 1:
        for i in range(len(spans)):
            first: dict[tuple, str] = {}
            for ln in by_rank:
                p, lab = cells[ln.id][i], labels[ln.id][i]
                if p is None or lab is None:
                    continue
                f = first.setdefault((lab, p % 12), ln.id)
                if f != ln.id:
                    local[ln.id][i] = f
    parts = []
    for ln in lines:
        cl, lb = cells[ln.id], labels[ln.id]
        notes: list[Note] = []
        for i, (p, s) in enumerate(zip(cl, spans)):
            if p is None:
                continue
            if i > 0 and tie[i - 1] and notes and notes[-1].pitch == p and notes[-1].end == s.start:
                notes[-1] = Note(p, notes[-1].start, s.end, velocity)
            else:
                notes.append(Note(p, s.start, s.end, velocity))
        sounding = [i for i, p in enumerate(cl) if p is not None]
        doubles = None
        for cand in prio[:pos[ln.id]]:
            cc, cb = cells[cand.id], labels[cand.id]
            if sounding:
                if all(cc[i] is not None and cb[i] == lb[i] and lb[i] is not None and cc[i] % 12 == cl[i] % 12
                       for i in sounding):
                    doubles = cand.id
                    break
            elif base[ln.id] is not None and base[cand.id] == base[ln.id]:
                doubles = cand.id
                break
        if ln.id in KEEP_LINE_BY_ID:
            group = KEEP_GROUP
        else:
            vs = {lb[i] for i in sounding} if sounding else {base[ln.id]}
            group = "low" if vs and vs <= {"B", "L5"} else None
        parts.append(Part(ln.id, ln.instrument, tuple(notes), ln.role, doubles, group, ln.label,
                          tuple(local[ln.id]) if len(spans) > 1 else None))
    return parts


def _must_fix(report: Report, rules: Rules, owned: set[str] = frozenset()) -> list:
    """Issues the generator must not produce. Issues only between fixed parts (owned) are the user's."""
    return [i for i in report.issues
            if (i.severity == "error" or rules.checks[i.check].generator_must_pass)
            and not (i.parts and set(i.parts) <= owned)]


# ---------------------------------------------------------------- voice leading
def _moves(a: int, b: int) -> int:
    return (b > a) - (b < a)


def _parallel(a1, a2, b1, b2) -> bool:
    """Same test as the checker: both move, not contrary, same 5th/octave class before and after."""
    if a1 == a2 or b1 == b2:
        return False
    if (a2 - a1 > 0) != (b2 - b1 > 0):
        return False
    iv1, iv2 = abs(a1 - b1) % 12, abs(a2 - b2) % 12
    return iv1 == iv2 and iv1 in (0, 7)


@dataclass
class _Fixed:
    """Fixed parts during a solve (locked parts, kept input voicing, a part regenerated on its own)."""
    lines: list[Line]
    cells: dict[str, list[int | None]]
    labels: dict[str, list[str | None]]

    @property
    def ids(self) -> set[str]:
        return {ln.id for ln in self.lines}

    def at(self, i: int) -> dict[str, int]:
        return {ln.id: self.cells[ln.id][i] for ln in self.lines if self.cells[ln.id][i] is not None}

    def choir_at(self, i: int) -> dict[str, int]:
        return {lid: p for lid, p in self.at(i).items() if lid in CHOIR_IDS}


class _Solver:
    def __init__(self, setup: _Setup, spans, key, seed, rules, insts, settings: Settings, fixed: _Fixed | None,
                 variation: int = 0, avoid: dict[str, list[int | None]] | None = None):
        self.setup, self.spans, self.key, self.rules, self.insts = setup, spans, key, rules, insts
        self.settings = settings
        self.fixed = fixed or _Fixed([], {}, {})
        self.seed_key = seed if variation == 0 else f"{seed}.{variation}"
        self.avoid = avoid
        self.same = _ties(spans)
        self.follow = settings.top_voice == TOP_INPUT
        self.velocity = VELOCITY  # candidates are checked at mf; velocity doesn't change any rule
        self.fixed_motion = bool(self.fixed.lines)
        rank = {sec: k for k, sec in enumerate(SECTION_PRIORITY)}
        self.all_lines = list(setup.lines) + self.fixed.lines
        order = {ln.id: k for k, ln in enumerate(self.all_lines)}
        self.prio_lines = sorted(self.all_lines, key=lambda ln: (rank[insts[ln.instrument].section], order[ln.id]))

    # --- per chord
    def valid(self, i: int, exclude_keys: set | None = None) -> list[_Cand]:
        span = self.spans[i]
        top = None
        if self.follow and i < len(self.settings.tops):
            top = self.settings.tops[i]
        fixed_now = self.fixed.at(i)
        avoid = None
        if self.avoid is not None:
            avoid = {lid: col[i] for lid, col in self.avoid.items() if lid in {ln.id for ln in self.setup.lines}}
        cands = _candidates(self.setup, span, self.key, self.seed_key, i, top=top,
                            fixed_pcs=frozenset(p % 12 for p in fixed_now.values()), avoid=avoid)
        if top is not None and not cands:  # the input's top note can't be the top voice here: smooth
            cands = _candidates(self.setup, span, self.key, self.seed_key, i,
                                fixed_pcs=frozenset(p % 12 for p in fixed_now.values()), avoid=avoid)
        owned = self.fixed.ids
        valid = []
        for c in cands[:MAX_CANDIDATES_CHECKED]:
            if exclude_keys and c.key in exclude_keys:
                continue
            parts = self.chord_parts(c, i)
            rep = check(parts, [span], self.key, SAFE, rules=self.rules, instruments=self.insts)
            if not _must_fix(rep, self.rules, owned):
                valid.append(c)
                if len(valid) >= KEEP[-1]:
                    break
        return valid

    def chord_parts(self, c: _Cand, i: int) -> list[Part]:
        """Checker parts for one chord (same links as build_parts; resting lines are left out)."""
        span = self.spans[i]
        fixed = self.fixed
        sound: dict[str, tuple[int, str | None]] = {}
        for ln in self.setup.lines:
            p = c.pd.get(ln.id)
            if p is not None:
                sound[ln.id] = (p, ln.voices[0])
        for ln in fixed.lines:
            p = fixed.cells[ln.id][i]
            if p is not None:
                sound[ln.id] = (p, fixed.labels[ln.id][i])
        first: dict[tuple, str] = {}
        for ln in self.prio_lines:
            if ln.id in sound:
                p, lab = sound[ln.id]
                first.setdefault((lab, p % 12), ln.id)
        parts = []
        for ln in self.all_lines:
            if ln.id not in sound:
                continue
            p, lab = sound[ln.id]
            d = first[(lab, p % 12)] if lab is not None else ln.id
            group = KEEP_GROUP if ln.id in KEEP_LINE_BY_ID else ("low" if lab in ("B", "L5") else None)
            parts.append(Part(ln.id, ln.instrument, (Note(p, span.start, span.end, self.velocity),), ln.role,
                              None if d == ln.id else d, group, ln.label))
        return parts

    # --- between chords
    def transition(self, a: _Cand, b: _Cand, i: int) -> float | None:
        """Cost of moving from voicing a (chord i-1) to b (chord i), or None if it breaks a hard rule."""
        setup = self.setup
        pc = setup.approach.parallel_cost
        if self.same[i - 1]:
            return 0.0 if a.key == b.key else 50.0
        # choir: leaps of at most an octave, no parallels between any two choir voices (hard rules)
        fa = fb = None
        if self.fixed_motion:
            fa, fb = self.fixed.choir_at(i - 1), self.fixed.choir_at(i)
        if setup.choir or fa or fb:
            if fa or fb:
                pa_, pb_ = dict(a.ch, **(fa or {})), dict(b.ch, **(fb or {}))
            else:
                pa_, pb_ = a.ch, b.ch
            ch = [lid for lid in pa_ if lid in pb_]
            for lid in ch:
                if abs(pb_[lid] - pa_[lid]) > 12:
                    return None
            for x, y in itertools.combinations(ch, 2):
                if _parallel(pa_[x], pb_[x], pa_[y], pb_[y]):
                    return None
        av, bv = a.vd, b.vd
        cost = 0.0
        for v in UPPER:
            if v in av and v in bv:
                d = abs(bv[v] - av[v])
                if d:
                    cost += 0.5 + 0.25 * d + 0.5 * max(0, d - 5) + 4.0 * max(0, d - 12)
        if not self.follow and "h4" in av and "h4" in bv:
            cost += 0.3 * abs(bv["h4"] - av["h4"])  # top voice: smooth (SPEC §5b default)
        cost += 0.05 * abs(bv["B"] - av["B"])
        bm = _moves(av["B"], bv["B"])
        for v in UPPER:
            if v in av and v in bv and bm and _moves(av[v], bv[v]) == -bm:
                cost -= 0.2  # contrary motion against the bass
        # parallels between independent lines (upper voices with each other and with the low group)
        ups = [v for v in UPPER if v in av and v in bv]
        for x, y in itertools.combinations(ups, 2):
            if _parallel(av[x], bv[x], av[y], bv[y]):
                cost += pc
        # the low group's real lines (some switch octave or switch between the open 5th and h1)
        pa, pb = a.pd, b.pd
        motions = {(pa[k], pb[k]) for k in setup.low_ids if pa.get(k) is not None and pb.get(k) is not None}
        for x in ups:
            for m1, m2 in motions:
                if _parallel(av[x], bv[x], m1, m2):
                    cost += pc
        if setup.switch_ids:  # lines that changed octave: their real motion against everything else
            extra = []
            for lid, x in setup.switch_ids:
                m1, m2 = pa.get(lid), pb.get(lid)
                if m1 is None or m2 is None or x not in av or x not in bv or m2 - m1 == bv[x] - av[x]:
                    continue
                extra.append((x, m1, m2))
            if extra:
                others = [(y, av[y], bv[y]) for y in ups] + [("low", m1, m2) for m1, m2 in motions]
                for k, (x, m1, m2) in enumerate(extra):
                    for y, n1, n2 in others + extra[k + 1:]:
                        if y != x and _parallel(m1, m2, n1, n2):
                            cost += pc
        if self.fixed_motion:  # parallels against fixed parts (locked, kept)
            f1, f2 = self.fixed.at(i - 1), self.fixed.at(i)
            fm = {(f1[k], f2[k]) for k in f1 if k in f2}
            for x in list(ups) + (["B"] if "B" in av and "B" in bv else []):
                for m1, m2 in fm:
                    if _parallel(av[x], bv[x], m1, m2):
                        cost += pc
        return cost

    def viterbi(self, layers: list[list[_Cand]]) -> list[_Cand] | None:
        best = [c.cost for c in layers[0]]
        back: list[list[int]] = []
        for i in range(1, len(layers)):
            cur, ptr = [], []
            for b in layers[i]:
                top, arg = None, -1
                for j, a in enumerate(layers[i - 1]):
                    if best[j] is None:
                        continue
                    t = self.transition(a, b, i)
                    if t is None:
                        continue
                    total = best[j] + t
                    if top is None or total < top:
                        top, arg = total, j
                cur.append(None if top is None else top + b.cost)
                ptr.append(arg)
            best, back = cur, back + [ptr]
            if all(x is None for x in best):
                return None
        end = min((j for j in range(len(best)) if best[j] is not None), key=lambda j: best[j])
        path = [end]
        for ptr in reversed(back):
            path.append(ptr[path[-1]])
        path.reverse()
        return [layers[i][j] for i, j in enumerate(path)]

    def solve(self) -> list[_Cand]:
        all_valid = []
        for i, span in enumerate(self.spans):
            valid = self.valid(i)
            if not valid:
                raise GenerationError(
                    f"No voicing of {span.label.symbol(self.key)} at {position_text(span.start)} passes the "
                    "rules with these instruments. Try turning more instruments on"
                    + (" or unlocking a part." if self.fixed.lines else "."))
            all_valid.append(valid)
        for keep in KEEP:
            path = self.viterbi([v[:keep] for v in all_valid])
            if path is not None:
                return path
        raise GenerationError("These chords can't be connected without breaking a choir rule "
                              "(a leap over an octave or parallel 5ths/octaves). Try turning the choir off"
                              + (" or unlocking a choir part." if self.fixed.lines else "."))


# ---------------------------------------------------------------- keep-as-is
def keep_assignment(voicings: tuple[tuple[int, ...], ...], insts: dict[str, Instrument]
                    ) -> dict[str, list[int | None]]:
    """Spread the input voicing over the string slots, low to high, one note per slot.

    Every note keeps its exact pitch. Each note goes to a slot whose instrument is comfortable for it
    (playable if none is; outside that it goes to the nearest slot and is flagged), slots in rising order.
    The lowest note goes to the basses when they can play it, and each note prefers the slot the note of
    the same rank used in the previous chord, so the lines stay steady.
    """
    n_slots = len(KEEP_SLOTS)
    cells: dict[str, list[int | None]] = {s[0]: [None] * len(voicings) for s in KEEP_SLOTS}
    prev: dict[int, int] = {}  # note rank (from the top: -1 = highest) -> slot used in the previous chord
    INF = float("inf")
    for ci, chord in enumerate(voicings):
        notes = sorted(set(chord))[:n_slots]
        if not notes:
            continue
        n = len(notes)

        def slot_cost(k: int, j: int) -> float:
            p = notes[j]
            _, inst, _, _, home = KEEP_SLOTS[k]
            ins = insts[inst]
            c = abs(p - home) * 0.1
            if not ins.is_comfortable(p):
                c += 50 if ins.is_playable(p) else 500
            if j == 0 and k == 0:
                c -= 2.0  # the bass note in the basses
            rank = j - n  # same rank counted from the top keeps its slot (melody stays in Violins I)
            if prev and prev.get(rank) is not None and prev[rank] != k:
                c += 0.8
            return c

        dp = [[INF] * n_slots for _ in range(n)]
        bk = [[-1] * n_slots for _ in range(n)]
        for k in range(n_slots):
            dp[0][k] = slot_cost(k, 0)
        for j in range(1, n):
            best, arg = INF, -1
            for k in range(n_slots):
                if k > 0 and dp[j - 1][k - 1] < best:
                    best, arg = dp[j - 1][k - 1], k - 1
                if best < INF:
                    dp[j][k] = best + slot_cost(k, j)
                    bk[j][k] = arg
        k = min(range(n_slots), key=lambda x: dp[n - 1][x])
        chosen = [0] * n
        for j in range(n - 1, -1, -1):
            chosen[j] = k
            k = bk[j][k]
        prev = {j - n: k for j, k in enumerate(chosen)}
        for j, k in enumerate(chosen):
            cells[KEEP_SLOTS[k][0]][ci] = notes[j]
    return cells


def _keep_labels(kc: dict[str, list[int | None]], spans: list[ChordSpan]) -> dict[str, list[str | None]]:
    """Voice labels for the kept lines: the lowest kept note is "B" when it is the chord's bass note (so
    model lines doubling it are linked to it), every other kept note is "keep"."""
    labels = {lid: [None if p is None else "keep" for p in col] for lid, col in kc.items()}
    for i, span in enumerate(spans):
        sounding = [(p, lid) for lid, col in kc.items() if (p := col[i]) is not None]
        if sounding:
            p, lid = min(sounding)
            if p % 12 == span.label.bass:
                labels[lid][i] = "B"
    return labels


# ---------------------------------------------------------------- public
def generate(chords: list[ChordSpan], key: Key, *, seed: int = 1, ensemble: Ensemble | None = None,
             mode: str = SAFE, rules: Rules | None = None, instruments: dict[str, Instrument] | None = None,
             approach: str = "A", settings: Settings | None = None,
             locked: Orchestration | None = None, locked_ids: frozenset[str] = frozenset(),
             variation: int = 0, avoid: Orchestration | None = None) -> Orchestration:
    """Orchestrate confirmed chords in safe mode with one approach. Raises GenerationError if impossible.

    locked / locked_ids: keep these parts of an earlier orchestration exactly and orchestrate around them.
    variation / avoid: "Regenerate" - a different seed variation, pushed away from the earlier result.
    """
    if mode != SAFE:
        raise ValueError("Generation is safe mode only until Milestone 5.")
    if not chords:
        raise GenerationError("There are no chords to orchestrate.")
    if approach not in APPROACH:
        raise ValueError(f"approach must be one of {APPROACHES}")
    rules = rules or builtin_rules()
    insts = instruments or builtin_instruments()
    settings = settings or Settings()
    if ensemble is not None:
        settings = replace(settings, ensemble=ensemble)
    ens = settings.ensemble
    ap = APPROACH[approach]
    spans = sorted(chords, key=lambda c: c.start)
    n = len(spans)
    keep = settings.keep is not None
    if keep and len(settings.keep) != n:
        raise ValueError("keep-as-is needs one input voicing per chord")
    all_lines = ensemble_lines(ens, insts, keep)
    if not all_lines:
        raise GenerationError("No instruments are active.")
    locked_ids = frozenset(lid for lid in locked_ids if locked is not None and lid in locked.cells
                           and any(ln.id == lid for ln in all_lines))
    # fixed parts: the kept voicing, then locked parts
    fixed_lines: list[Line] = []
    fcells: dict[str, list[int | None]] = {}
    flabels: dict[str, list[str | None]] = {}
    if keep:
        kc = keep_assignment(settings.keep, insts)
        kl = _keep_labels(kc, spans)
        for ln in KEEP_LINES:
            fixed_lines.append(ln)
            fcells[ln.id] = kc[ln.id]
            flabels[ln.id] = kl[ln.id]
    for ln in all_lines:
        if ln.id in locked_ids and ln.id not in fcells:
            fixed_lines.append(ln)
            fcells[ln.id] = list(locked.cells[ln.id])
            # unique labels while solving: new lines never count as doubling a locked one
            flabels[ln.id] = [None if lab is None else f"lock:{lab}" for lab in locked.meta["labels"][ln.id]]
    fixed = _Fixed(fixed_lines, fcells, flabels) if fixed_lines else None
    model_lines = approach_lines(ap, ens, insts, exclude=set(fcells), keep=keep)
    has_fixed = fixed is not None and any(fixed.at(i) for i in range(n))
    cells: dict[str, list[int | None]] = {ln.id: [None] * n for ln in all_lines}
    labels: dict[str, list[str | None]] = {ln.id: [None] * n for ln in all_lines}
    voicing: list[dict] = [{} for _ in range(n)]
    if model_lines:
        setup = _Setup(model_lines, insts, ap, need_bass=not has_fixed)
        prev = None
        if avoid is not None:
            prev = {ln.id: avoid.cells[ln.id] for ln in model_lines if ln.id in avoid.cells}
        solver = _Solver(setup, spans, key, seed, rules, insts, settings, fixed, variation, prev)
        path = solver.solve()
        for ln in model_lines:
            cells[ln.id] = [c.p(ln.id) for c in path]
            labels[ln.id] = [ln.voices[0] if p is not None else None for p in cells[ln.id]]
        voicing = [dict(c.voices) for c in path]
    if fixed is not None:
        for ln in fixed.lines:
            cells[ln.id] = list(fixed.cells[ln.id])
            labels[ln.id] = list(locked.meta["labels"][ln.id]) if ln.id in locked_ids else list(fixed.labels[ln.id])
    meta = {"voices": voicing, "labels": labels, "settings": settings, "variation": variation,
            "sources": [approach] * n, "fixed": set(fcells), "model": [ln.id for ln in model_lines],
            "free": set(), "origin": None}
    orch = _finish(approach, key, seed, spans, all_lines, cells, meta, settings, rules, insts)
    bad = _must_fix(orch.report, rules, set(fcells))
    if bad:  # should never happen: every rule is enforced above
        raise GenerationError("The generated result failed the rule checker, so it was discarded:\n"
                              + "\n".join(i.message for i in bad))
    return orch


def _finish(approach, key, seed, spans, lines, cells, meta, settings: Settings, rules, insts,
            reason: str | None = None) -> Orchestration:
    vel = settings.velocity
    parts = build_parts(lines, spans, cells, meta["labels"], vel, insts)
    report = check(parts, spans, key, SAFE, rules=rules, instruments=insts)
    if reason is None:
        reason = _reason(APPROACH[approach], lines, cells, insts, settings)
    return Orchestration(approach, reason, key, SAFE, seed, list(spans), list(lines), parts, cells, report,
                         vel, vel, meta)


def generate_all(chords, key, *, seed: int = 1, settings: Settings | None = None,
                 locks: dict[str, frozenset[str]] | None = None,
                 previous: dict[str, Orchestration | None] | None = None, rules=None, instruments=None
                 ) -> dict[str, Orchestration | GenerationError]:
    """All three alternatives. Locked parts (per alternative) are kept from `previous`."""
    out = {}
    for a in APPROACHES:
        prev = (previous or {}).get(a)
        ids = (locks or {}).get(a, frozenset()) if prev is not None else frozenset()
        try:
            out[a] = generate(chords, key, seed=seed, approach=a, settings=settings, locked=prev,
                              locked_ids=ids, rules=rules, instruments=instruments)
        except GenerationError as exc:
            out[a] = exc
    return out


def with_dynamics(orch: Orchestration, dynamics: str, rules=None, instruments=None) -> Orchestration:
    """The same notes at another dynamic (velocity and CC1). Nothing is regenerated."""
    settings = replace(orch.settings, dynamics=dynamics)
    meta = dict(orch.meta, settings=settings)
    insts = instruments or builtin_instruments()
    vel = settings.velocity
    parts = [replace(p, notes=tuple(Note(n.pitch, n.start, n.end, vel) for n in p.notes)) for p in orch.parts]
    return replace(orch, parts=parts, velocity=vel, cc1=vel, meta=meta)


def _reason(ap: Approach, lines: list[Line], cells, insts, settings: Settings) -> str:
    """One line on what this alternative does, from what actually plays."""
    playing = {ln.id for ln in lines if any(p is not None for p in cells[ln.id])}
    secs = {insts[LINE_BY_ID.get(lid, KEEP_LINE_BY_ID.get(lid)).instrument].section for lid in playing}
    has = playing.__contains__
    horns = any(has(f"hn{i}") for i in range(1, 5))
    bits = []
    if settings.keep is not None:
        bits.append("your voicing kept in the strings")
    if ap.id == "A":
        if "strings" in secs and horns:
            bits.append("close mid-register chord in strings and horns")
        elif "strings" in secs:
            bits.append("close mid-register chord in the strings")
        elif horns:
            bits.append("close mid-register chord in the horns")
        else:
            bits.append("close mid-register chord")
        if any(has(i) for i in ("bn1", "tbn2", "vc-b")):
            bits.append("low brass and bassoons in open 5ths over the bass" if (has("tbn2") or has("bn1"))
                        else "cellos in open 5ths over the bass")
        if any(has(i) for i in ("cb", "cb-solo")):
            bits.append("basses an octave under the cellos")
        if "woodwinds" in secs:
            bits.append("woodwinds doubling at the unison")
    elif ap.id == "B":
        bits.append("widest span")
        if has("vln1-a") or has("vln1-solo"):
            bits.append("Violins I in octaves on top")
        if has("fl1") or has("picc"):
            bits.append("flutes" + (" and piccolo" if has("picc") else "") + " an octave up")
        if horns:
            bits.append("horns filling the middle")
        if any(has(i) for i in ("cb", "cbn", "tba")):
            bits.append("basses, tuba and contrabassoon an octave down" if has("tba") or has("cbn")
                        else "basses an octave down")
        if has("tbn2") or has("bn1"):
            bits.append("open 5ths in the low brass")
    else:
        lead = [n for n, ok in (("violins", has("vln1-a") or has("vln1-solo")),
                                ("flutes" + (" and piccolo" if has("picc") else ""), has("fl1") or has("picc")),
                                ("trumpets", has("tpt1"))) if ok]
        bits.append("upper voices high" + (", led by " + ", ".join(lead) if lead else ""))
        if horns:
            bits.append("horns in the middle")
        bits.append("light bass without tuba or contrabassoon" if ("brass" in secs or "woodwinds" in secs)
                    else "light bass")
    if any(lid in playing for lid in CHOIR_IDS):
        n_ch = sum(lid in playing for lid in CHOIR_IDS)
        bits.append("choir in four parts" if n_ch == 4 else f"choir in {n_ch} parts")
    text = ", ".join(bits)
    return f"{ap.name}: {text[0].lower() + text[1:] if text else text}."
