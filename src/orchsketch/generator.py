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

from . import patterns as pat
from .analysis.chords import QUALITIES, ChordLabel
from .checker import ChordSpan, Issue, Part, Report, check, required_tones
from .instruments import SECTIONS, Instrument, instruments as builtin_instruments
from .midi_io import TOLERANCE, Note, position_text
from .rules import MODERATE, SAFE, WARNING, Rules, rules as builtin_rules
from .theory import Key, note_name

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
CHARACTERS = (SAFE, MODERATE)
TOP_SMOOTH, TOP_INPUT = "smooth", "input"
DOUBLINGS = ("auto", "off", "up", "down")  # melody octave doubling

# Search sizes. KEEP valid candidates per chord go into the path search; more if no path is found.
KEEP = (40, 200)
MAX_CANDIDATES_CHECKED = 2500

BASS_WINDOW = (40, 51)  # the bass voice: E2..Eb3, one octave so octave doublings stay fixed
HEROIC = (53, 65)  # horn F3..F4
PARALLEL_COST = 8.0  # parallel 5ths/8ves between independent lines (a checker warning): avoided when possible
SAME_AS_BEFORE_COST = 2.0  # "Regenerate" pushes away from the previous results
REGEN_MEMORY = 8  # Regenerate avoids this many earlier variations (not just the last one)
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


def _pairs(d) -> tuple[tuple[str, object], ...]:
    """A dict (or pairs) as sorted pairs, so settings stay hashable and compare equal."""
    if not d:
        return ()
    items = d.items() if isinstance(d, dict) else d
    return tuple(sorted((str(k), v) for k, v in items))


@dataclass(frozen=True)
class Ensemble:
    """Which instruments play, plus the Forces and Density sliders.

    `Ensemble(sections)` turns whole sections on (Milestone 3 toggles); presets pass `instruments`.
    `forces` / `density` are the master values; `section_forces` / `section_density` override them per section
    (SPEC §6 per-section sliders). With no overrides every section uses the master value.
    """
    sections: frozenset[str] = frozenset(SECTIONS)
    instruments: frozenset[str] | None = None
    forces: str = "section"
    density: int = 5
    section_forces: tuple = ()  # (section, forces) pairs
    section_density: tuple = ()  # (section, density) pairs

    def __post_init__(self):
        bad = set(self.sections) - set(SECTIONS)
        if bad:
            raise ValueError(f"unknown section(s) {sorted(bad)}")
        object.__setattr__(self, "section_forces", _pairs(self.section_forces))
        object.__setattr__(self, "section_density", _pairs(self.section_density))
        for sec, _ in self.section_forces + self.section_density:
            if sec not in SECTIONS:
                raise ValueError(f"unknown section {sec!r}")
        if self.forces not in FORCES or any(f not in FORCES for _, f in self.section_forces):
            raise ValueError(f"forces must be one of {FORCES}")
        if self.density not in DENSITY_STEPS or any(d not in DENSITY_STEPS for _, d in self.section_density):
            raise ValueError("density must be 1-5")
        if self.instruments is not None:
            object.__setattr__(self, "instruments", frozenset(self.instruments))
            if not self.instruments:
                raise ValueError("at least one instrument must play")
        elif not self.sections:
            raise ValueError("at least one section must play")

    def forces_for(self, section: str) -> str:
        return dict(self.section_forces).get(section, self.forces)

    def density_for(self, section: str) -> int:
        return dict(self.section_density).get(section, self.density)

    def active(self, insts: dict[str, Instrument]) -> frozenset[str]:
        if self.instruments is not None:
            unknown = self.instruments - set(insts)
            if unknown:
                raise ValueError(f"unknown instrument(s) {sorted(unknown)}")
            return self.instruments
        return frozenset(i for i, inst in insts.items() if inst.section in self.sections)


@dataclass(frozen=True)
class Settings:
    """Everything besides chords, key and seed that shapes a generation.

    Per-section values (`section_*`) override the master value for that section. Defaults give exactly the
    Milestone 4 result: safe mode, Sustain everywhere, no melody or bass file.
    """
    ensemble: Ensemble = Ensemble()
    top_voice: str = TOP_SMOOTH  # "smooth" or "input"
    tops: tuple[int | None, ...] = ()  # the input clip's top note per chord (for "input")
    keep: tuple[tuple[int, ...], ...] | None = None  # the input voicing per chord, kept in the strings
    dynamics: str = "mf"
    section_dynamics: tuple = ()  # (section, dynamics) pairs
    character: str = SAFE  # Character slider: "safe" or "moderate"
    section_character: tuple = ()  # (section, character) pairs
    pattern: str = pat.SUSTAIN  # master rhythm pattern
    section_patterns: tuple = ()  # (section, pattern) pairs
    instrument_patterns: tuple = ()  # (instrument id, pattern) pairs (presets, e.g. low brass)
    part_patterns: tuple = ()  # (line id, pattern) pairs: per-part overrides
    restrike_bars: bool = False  # Sustain re-strikes every bar instead of holding ties
    note_mode: str = pat.CHORD_TONES  # how a pattern's contour steps (chord tones / hybrid / scale steps)
    section_note_modes: tuple = ()  # (section, note mode) pairs
    accent: str = pat.PATTERN_ACCENTS  # accent grouping of grid patterns ("pattern": the pattern's own)
    section_accents: tuple = ()  # (section, accent grouping) pairs
    part_variants: tuple = ()  # (line id, (pattern, accent)) pairs: a pattern alternative's choices (2 and 3)
    melody: tuple[Note, ...] | None = None  # the melody file's notes (SPEC §5 step 3)
    bass: tuple[Note, ...] | None = None  # the bass file's notes (SPEC §5 step 2)
    melody_instrument: str | None = None  # None: chosen by register and approach
    melody_double: str = "auto"  # auto / off / up / down
    independent_bass: bool = False  # moderate only: a bass line moving by step toward the next chord

    def __post_init__(self):
        for f in ("section_dynamics", "section_character", "section_patterns", "instrument_patterns",
                  "part_patterns", "section_note_modes", "section_accents", "part_variants"):
            object.__setattr__(self, f, _pairs(getattr(self, f)))
        if self.dynamics not in DYNAMICS or any(d not in DYNAMICS for _, d in self.section_dynamics):
            raise ValueError("dynamics must be one of " + " ".join(DYNAMICS))
        if self.character not in CHARACTERS or any(c not in CHARACTERS for _, c in self.section_character):
            raise ValueError("character must be safe or moderate")
        if self.pattern not in pat.PATTERNS or any(p not in pat.PATTERNS for _, p in self.section_patterns
                                                   + self.instrument_patterns + self.part_patterns):
            raise ValueError("unknown rhythm pattern")
        if self.note_mode not in pat.NOTE_MODES or any(m not in pat.NOTE_MODES for _, m in self.section_note_modes):
            raise ValueError("note mode must be one of " + " ".join(pat.NOTE_MODES))
        if self.accent not in pat.ACCENTS or any(a not in pat.ACCENTS for _, a in self.section_accents):
            raise ValueError("unknown accent grouping")
        object.__setattr__(self, "part_variants", tuple((k, tuple(v)) for k, v in self.part_variants))
        for _, v in self.part_variants:
            if not (isinstance(v, tuple) and len(v) == 2 and v[0] in pat.PATTERNS and v[1] in pat.ACCENTS):
                raise ValueError("a pattern variant is (pattern, accent grouping)")
        if self.melody_double not in DOUBLINGS:
            raise ValueError(f"melody doubling must be one of {DOUBLINGS}")
        for f in ("melody", "bass"):
            v = getattr(self, f)
            if v is not None:
                object.__setattr__(self, f, tuple(sorted(v, key=lambda n: n.start)) or None)

    @property
    def velocity(self) -> int:
        return DYNAMICS[self.dynamics]

    def dynamics_for(self, section: str) -> str:
        return dict(self.section_dynamics).get(section, self.dynamics)

    def velocity_for(self, section: str) -> int:
        return DYNAMICS[self.dynamics_for(section)]

    def character_for(self, section: str) -> str:
        return dict(self.section_character).get(section, self.character)

    def pattern_for(self, line_id: str, section: str, instrument: str | None = None, base: bool = False) -> str:
        """A pattern alternative's choice, else part override, else instrument (presets), else section, else
        the master pattern. base=True leaves out the pattern alternative (pattern 1's choice)."""
        if not base and line_id in dict(self.part_variants):
            return dict(self.part_variants)[line_id][0]
        if line_id in dict(self.part_patterns):
            return dict(self.part_patterns)[line_id]
        if instrument is not None and instrument in dict(self.instrument_patterns):
            return dict(self.instrument_patterns)[instrument]
        return dict(self.section_patterns).get(section, self.pattern)

    def note_mode_for(self, section: str) -> str:
        return dict(self.section_note_modes).get(section, self.note_mode)

    def accent_for(self, line_id: str, section: str, base: bool = False) -> str:
        if not base and line_id in dict(self.part_variants):
            return dict(self.part_variants)[line_id][1]
        return dict(self.section_accents).get(section, self.accent)

    def mode(self, sections=SECTIONS) -> str:
        """The checker mode: moderate when any of these sections is moderate."""
        return MODERATE if any(self.character_for(s) == MODERATE for s in sections) else SAFE


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

    def section_of(self, line_id: str) -> str:
        return builtin_instruments()[self.line(line_id).instrument].section

    def cc1_for(self, line_id: str) -> int:
        """The part's constant CC1 value (its section's Dynamics; SPEC §6)."""
        return self.settings.velocity_for(self.section_of(line_id))

    @property
    def figures(self) -> dict:
        return self.meta.get("figures") or {}

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
    out = [ln for ln in LINES if ln.instrument in active
           and ensemble.forces_for(insts[ln.instrument].section) in ln.forces]
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
    dens = {insts[ln.instrument].section: ensemble.density_for(insts[ln.instrument].section) for ln in lines}
    if dens and min(dens.values()) < 5:
        lines = _thin(lines, approach, insts, {sec: DENSITY_K[d] for sec, d in dens.items()})
    return _anchor_octaves(lines, insts)


DENSITY_K = {1: 1, 2: 2, 3: 3, 4: 5, 5: 10 ** 6}  # lines kept per voice at each Density step


def _thin(lines: list[Line], approach: Approach, insts, k) -> list[Line]:
    """Density: keep the k most important lines per voice (approach lead order). The choir plays as a
    whole, and each section keeps its voices contiguous (no gaps over an octave inside a section).

    `k` is one number, or a number per section (per-section Density sliders): then the lines are first kept
    as for the highest k, and a section with a lower k keeps only its own k most important lines per voice.
    With the same k everywhere this is exactly the single-number rule."""
    lead = {lid: i for i, lid in enumerate(approach.lead)}
    score = {ln.id: i for i, ln in enumerate(LINES)}
    sec_of = {ln.id: insts[ln.instrument].section for ln in lines}
    ks = k if isinstance(k, dict) else {sec: k for sec in sec_of.values()}
    kmax = max(ks.values())

    def importance(ln):
        return lead.get(ln.id, 100 + score.get(ln.id, 0))

    keepers: set[str] = set()
    for v in VOICES:
        carriers = sorted((ln for ln in lines if ln.voices[0] == v), key=importance)
        kept = carriers[:kmax]
        rank: dict[str, int] = {}
        for ln in kept:
            sec = sec_of[ln.id]
            rank[sec] = rank.get(sec, 0) + 1
            if rank[sec] <= ks[sec]:
                keepers.add(ln.id)
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
                 need_bass: bool = True, settings: Settings | None = None):
        self.inst = insts
        self.approach = approach
        self.lines = lines
        settings = settings or Settings()
        # moderate mode (per section): lines that may reach playable range
        self.moderate = {ln.id for ln in lines if settings.character_for(insts[ln.instrument].section) == MODERATE}
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
        self.by_id = {ln.id: ln for ln in self.lines}
        if need_bass and "B" not in self.primary:
            raise GenerationError("Nothing can play the bass line with these instruments.")
        # moderate: upper voices whose every line is in a moderate section may take a colour tone
        self.colour_voices = {v for v in UPPER if any(ln.voices[0] == v for ln in self.lines)
                              and all(ln.id in self.moderate for ln in self.lines if ln.voices[0] == v)}

    def comfortable(self, line: Line, pitch: int) -> bool:
        return self.inst[line.instrument].is_comfortable(pitch)

    def in_range(self, line: Line, pitch: int) -> bool:
        """Comfortable range, or playable range for a line in a moderate section."""
        inst = self.inst[line.instrument]
        return inst.is_comfortable(pitch) or (line.id in self.moderate and inst.is_playable(pitch))

    def line_pitch(self, line: Line, voices: dict[str, int]) -> int | None:
        for v in line.voices:
            if v in voices:
                for off in line.octaves:
                    p = voices[v] + off
                    if self.comfortable(line, p):
                        return p
                if line.id in self.moderate:  # moderate: playable range, flagged yellow
                    for off in line.octaves:
                        p = voices[v] + off
                        if self.inst[line.instrument].is_playable(p):
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


COLOUR_COST = 1.3  # moderate: a colour tone costs a little, so roughly 40-45% of chords get one
NO_L5_COST = 0.6  # with a moving bass line the open 5th may rest


def colour_pcs(label: ChordLabel, key: Key) -> set[int]:
    """Moderate mode (SPEC §5b): diatonic 9th, sus 4th colour and added 6th for this chord, if any.
    No colour on diminished, augmented or half-diminished chords; no 4th over a major 3rd."""
    if label.quality in ("dim", "aug", "dim7", "m7b5"):
        return set()
    ivs = QUALITIES[label.quality][0]
    pcs, scale = label.pcs(), key.scale_pcs()
    out = set()
    for iv in (2, 5, 9):
        pc = (label.root + iv) % 12
        if pc in pcs or pc not in scale:
            continue
        if iv == 5 and 4 in ivs:
            continue
        out.add(pc)
    return out


def _candidates(setup: _Setup, span: ChordSpan, key: Key, seed, index: int, *, top: int | None = None,
                fixed_pcs: frozenset[int] = frozenset(), avoid: dict[str, int | None] | None = None,
                bass_pin: int | None = None, mel_lo: int | None = None, l5_optional: bool = False
                ) -> list[_Cand]:
    """Every voicing of the chord for the model lines, cheapest first.

    bass_pin: the bass voice's pitch is given (a bass file or independent bass line plays it).
    mel_lo: the melody's lowest note in this chord; upper voices above it cost a little (voiced around it).
    l5_optional: the open 5th may also rest (used with a moving bass line).
    Moderate sections add voicings with one colour tone (colour_pcs) in an upper voice.
    """
    label = span.label
    chord_pcs = label.pcs()
    sens = _sensitive_pcs(label, key)
    need = set(required_tones(label)) - set(fixed_pcs)
    ivs = QUALITIES[label.quality][0]
    bass_pc = label.bass if bass_pin is None else bass_pin % 12
    root_pos = bass_pc == label.root
    want_l5 = root_pos and 7 in ivs and any("L5" in ln.voices for ln in setup.lines)
    rng = random.Random(f"{seed}:{index}:{label.root}:{label.quality}:{label.bass}")
    lo, hi = setup.approach.upper_window
    tones = [p for p in range(lo, hi + 1) if p % 12 in chord_pcs]
    n_up = len(setup.upper)
    top_pc, top_target = _input_top(setup, label, top)
    colours = colour_pcs(label, key) if setup.colour_voices and n_up else set()
    ctones = [p for p in range(lo, hi + 1) if p % 12 in colours]
    choir_ranges = {}
    for v, lid in setup.choir_lines.items():
        if v != "B" and v in setup.upper:
            inst = setup.inst[CHOIR_INSTRUMENTS[lid]]
            choir_ranges[v] = inst.playable if lid in setup.moderate else inst.comfortable
    out: list[_Cand] = []
    seen = set()

    def consider(bass: int, ups: tuple[int, ...], colour: int | None):
        # adjacent upper voices: at most an octave apart; unisons allowed (needed e.g. for a choir
        # on power chords) but never three voices on one note
        if any(b - a > 12 for a, b in zip(ups, ups[1:])):
            return
        if any(a == c for a, c in zip(ups, ups[2:])):
            return
        if ups and ups[0] <= bass:
            return
        if top_pc is not None and ups and ups[-1] % 12 != top_pc:
            return
        voices = {"B": bass}
        for v, p in zip(setup.upper, ups):
            voices[v] = p
        if colour is not None:
            cv = setup.upper[ups.index(colour)]
            if cv not in setup.colour_voices:
                return
        with_l5 = want_l5 and (not ups or bass + 7 < ups[0])
        for l5 in ((True, False) if with_l5 and l5_optional else (with_l5,)):
            vs = dict(voices, L5=bass + 7) if l5 else voices
            _consider_voices(vs, ups, colour, NO_L5_COST if with_l5 and not l5 else 0.0)

    def _consider_voices(voices, ups, colour, extra):
        # leading tone / chord 7th in at most one line family (bass + L5 count as one)
        up_pcs = [p % 12 for p in ups]
        low_pcs = {bass_pc} | ({(voices["B"] + 7) % 12} if "L5" in voices else set())
        if any(up_pcs.count(pc) + (pc in low_pcs) > 1 for pc in sens):
            return
        if not need <= set(up_pcs) | low_pcs:
            return
        if colour is not None:  # a colour tone never sits a semitone from another sounding voice
            if any(abs(colour - q) == 1 for q in voices.values()):
                return
        if any(not (r[0] <= voices[v] <= r[1]) for v, r in choir_ranges.items()):
            return
        pitches: dict[str, int | None] = {ln.id: (None if ln.id == CHOIR_BASS else setup.line_pitch(ln, voices))
                                          for ln in setup.lines}
        # every voice's primary line must sound it (the choir bass is placed below)
        if any(pitches.get(setup.primary[v]) is None for v in voices
               if v in setup.primary and setup.primary[v] != CHOIR_BASS):
            return
        bass_opts = [None]
        if setup.choir:
            tenor = voices.get(next((v for v, lid in setup.choir_lines.items() if lid == "ch-t"), "-"), 127)
            r = setup.inst["choir_bass"].playable if CHOIR_BASS in setup.moderate else setup.inst["choir_bass"].comfortable
            bass_opts = [p for p in range(r[0], r[1] + 1) if p % 12 == bass_pc and p <= tenor]
            if not bass_opts:
                return
        for cb in bass_opts:
            if cb is not None:
                pitches = dict(pitches, **{CHOIR_BASS: cb})
            key_ = tuple(sorted(pitches.items()))
            if key_ in seen:
                continue
            seen.add(key_)
            cost = _vertical_cost(setup, label, voices, pitches, rng, top_target)
            if avoid is not None:  # Regenerate: away from earlier results (one dict, or a list of them)
                for av in (avoid if isinstance(avoid, list) else [avoid]):
                    if all(pitches.get(k) == p for k, p in av.items()):
                        cost += SAME_AS_BEFORE_COST
            if colour is not None:
                cost += COLOUR_COST
            if mel_lo is not None and ups:
                cost += 0.3 * max(0, max(ups) - mel_lo)
            if setup.moderate:
                cost += 0.5 * sum(1 for lid, p in pitches.items() if p is not None
                                  and not setup.inst[_line_inst(setup, lid)].is_comfortable(p))
            out.append(_Cand(tuple(sorted(voices.items())), tuple(pitches.items()), cost + extra))

    basses = [bass_pin] if bass_pin is not None else [b for b in range(BASS_WINDOW[0], BASS_WINDOW[1] + 1)
                                                      if b % 12 == label.bass]
    for bass in basses:
        for ups in itertools.combinations_with_replacement(tones, n_up):
            consider(bass, ups, None)
        for c in ctones:  # moderate: one colour tone in one upper voice
            for rest in itertools.combinations_with_replacement(tones, n_up - 1):
                consider(bass, tuple(sorted(rest + (c,))), c)
    out.sort(key=lambda c: c.cost)
    return out


def _line_inst(setup: _Setup, line_id: str) -> str:
    return setup.by_id[line_id].instrument


# ---------------------------------------------------------------- parts
def _ties(spans: list[ChordSpan]) -> list[bool]:
    """tie[i]: chord i+1 repeats chord i (common notes are held)."""
    return [spans[i].label == spans[i + 1].label and spans[i].end == spans[i + 1].start
            for i in range(len(spans) - 1)]


def build_parts(lines: list[Line], spans: list[ChordSpan], cells: dict[str, list[int | None]],
                labels: dict[str, list[str | None]], velocity: int, insts: dict[str, Instrument],
                tie: list[bool] | None = None, notes: dict[str, list[Note]] | None = None) -> list[Part]:
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
    given = notes or {}
    for ln in lines:
        cl, lb = cells[ln.id], labels[ln.id]
        if ln.id in given:
            notes = list(given[ln.id])
        else:
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


# A figure: one part's notes inside one chord, relative to the part's cell pitch at that chord:
# (start tick, end tick, semitones from the cell pitch, tied to the previous chord's last note).
Figure = tuple[tuple[int, int, int, bool], ...]


def figure_notes(cell: int | None, fig: Figure | None, span: ChordSpan, velocity: int) -> list[Note]:
    """The notes of one part at one chord: its figure (melody, bass file) or one note for the chord."""
    if cell is None:
        return []
    if fig is None:
        return [Note(cell, span.start, span.end, velocity)]
    return [Note(cell + d, s, e, velocity) for s, e, d, _ in fig]


def _fig_end(cell: int, fig: Figure | None) -> int:
    """The part's top note at the chord's last attack (what the checker's melodic checks follow)."""
    if not fig:
        return cell
    last = max(f[0] for f in fig)
    return cell + max(f[2] for f in fig if f[0] == last)


@dataclass
class _Fixed:
    """Fixed parts during a solve (locked parts, kept input voicing, a part regenerated on its own, the
    melody and the bass file lines). `figures` gives the rhythm of lines that don't simply sustain."""
    lines: list[Line]
    cells: dict[str, list[int | None]]
    labels: dict[str, list[str | None]]
    figures: dict[str, list[Figure | None]] = field(default_factory=dict)
    # lookups the search asks for again and again (v1.2 speed-up); forget() after changing figures
    _memo: dict = field(default_factory=dict, repr=False, compare=False)

    def forget(self):
        self._memo.clear()

    def _cached(self, k, fn):
        v = self._memo.get(k)
        if v is None:
            v = self._memo[k] = fn()
        return v

    @property
    def ids(self) -> set[str]:
        return {ln.id for ln in self.lines}

    def at(self, i: int) -> dict[str, int]:
        return self._cached(("at", i), lambda: {ln.id: self.cells[ln.id][i] for ln in self.lines
                                                if self.cells[ln.id][i] is not None})

    def end_at(self, i: int) -> dict[str, int]:
        """Pitch at the chord's last attack (the start pitch unless the line has a figure)."""
        return self._cached(("end", i), lambda: {
            lid: _fig_end(p, self.figures[lid][i] if lid in self.figures else None) for lid, p in self.at(i).items()})

    @property
    def choir_ids(self) -> set[str]:
        """Fixed lines sung by the choir: its own lines, and a melody given to a choir voice (line "mel")."""
        return self._cached(("choir",), lambda: {ln.id for ln in self.lines
                                                 if ln.id in CHOIR_IDS or ln.instrument in CHOIR_INSTRUMENTS.values()})

    def choir_at(self, i: int) -> dict[str, int]:
        ids = self.choir_ids
        return self._cached(("choir_at", i), lambda: {lid: p for lid, p in self.at(i).items() if lid in ids})

    def choir_end_at(self, i: int) -> dict[str, int]:
        ids = self.choir_ids
        return self._cached(("choir_end", i), lambda: {lid: p for lid, p in self.end_at(i).items() if lid in ids})

    def notes(self, line_id: str, i: int, span: ChordSpan, velocity: int) -> list[Note]:
        fig = self.figures[line_id][i] if line_id in self.figures else None
        return figure_notes(self.cells[line_id][i], fig, span, velocity)


class _Solver:
    def __init__(self, setup: _Setup, spans, key, seed, rules, insts, settings: Settings, fixed: _Fixed | None,
                 variation: int = 0, avoid: dict[str, list[int | None]] | None = None,
                 extras: dict | None = None):
        self.setup, self.spans, self.key, self.rules, self.insts = setup, spans, key, rules, insts
        self.settings = settings
        self.mode = settings.mode()
        # per chord: "bass_pin" (bass voice pitch), "mel_lo" (melody's lowest note); "l5_optional"
        self.extras = extras or {}
        self.on_empty = None  # callback(i) -> True if it changed the fixed parts so chord i can be retried
        self.fixed = fixed or _Fixed([], {}, {})
        self.seed_key = seed if variation == 0 else f"{seed}.{variation}"
        self.avoid = avoid
        self.same = _ties(spans)
        self.follow = settings.top_voice == TOP_INPUT
        self.velocity = VELOCITY  # candidates are checked at mf; velocity doesn't change any rule
        self.fixed_motion = bool(self.fixed.lines)
        self.melody_ids = [ln.id for ln in self.fixed.lines if ln.role == "melody"]
        self.model_ids = [ln.id for ln in setup.lines]
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
            ids = {ln.id for ln in self.setup.lines}
            avoid = [{lid: col[i] for lid, col in av.items() if lid in ids}
                     for av in (self.avoid if isinstance(self.avoid, list) else [self.avoid])]
        ex = {k: (v[i] if isinstance(v, list) else v) for k, v in self.extras.items()}
        cands = _candidates(self.setup, span, self.key, self.seed_key, i, top=top,
                            fixed_pcs=frozenset(p % 12 for p in fixed_now.values()), avoid=avoid, **ex)
        if top is not None and not cands:  # the input's top note can't be the top voice here: smooth
            cands = _candidates(self.setup, span, self.key, self.seed_key, i,
                                fixed_pcs=frozenset(p % 12 for p in fixed_now.values()), avoid=avoid, **ex)
        owned = self.fixed.ids
        valid = []
        for c in cands[:MAX_CANDIDATES_CHECKED]:
            if exclude_keys and c.key in exclude_keys:
                continue
            parts = self.chord_parts(c, i)
            rep = check(parts, [span], self.key, self.mode, rules=self.rules, instruments=self.insts,
                        inside=False)
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
        fixed_ids = fixed.ids
        for ln in self.all_lines:
            if ln.id not in sound:
                continue
            p, lab = sound[ln.id]
            d = first[(lab, p % 12)] if lab is not None else ln.id
            group = KEEP_GROUP if ln.id in KEEP_LINE_BY_ID else ("low" if lab in ("B", "L5") else None)
            notes = (tuple(fixed.notes(ln.id, i, span, self.velocity)) if ln.id in fixed_ids
                     else (Note(p, span.start, span.end, self.velocity),))
            parts.append(Part(ln.id, ln.instrument, notes, ln.role, None if d == ln.id else d, group, ln.label))
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
            fa, fb = self.fixed.choir_end_at(i - 1), self.fixed.choir_at(i)
        if setup.choir or fa or fb:
            if fa or fb:
                pa_, pb_ = dict(a.ch, **(fa or {})), dict(b.ch, **(fb or {}))
            else:
                pa_, pb_ = a.ch, b.ch
            ch = [lid for lid in pa_ if lid in pb_]
            # problems only between your own fixed parts (melody, bass file, locks) are shown, not refused
            mine = set(fa or {}) | set(fb or {})
            for lid in ch:
                if lid not in mine and abs(pb_[lid] - pa_[lid]) > 12:
                    return None
            for x, y in itertools.combinations(ch, 2):
                if not (x in mine and y in mine) and _parallel(pa_[x], pb_[x], pa_[y], pb_[y]):
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
        if self.fixed_motion:  # parallels against fixed parts (locked, kept, melody, bass file)
            f1, f2 = self.fixed.end_at(i - 1), self.fixed.at(i)
            fm = {(f1[k], f2[k]) for k in f1 if k in f2}
            for x in list(ups) + (["B"] if "B" in av and "B" in bv else []):
                for m1, m2 in fm:
                    if _parallel(av[x], bv[x], m1, m2):
                        cost += pc
            if self.melody_ids:  # the melody against every real model line (octave doublings included)
                mm = {(f1[k], f2[k]) for k in self.melody_ids if k in f1 and k in f2}
                if mm:
                    lm = {(pa[k], pb[k]) for k in self.model_ids if pa.get(k) is not None and pb.get(k) is not None}
                    for m1, m2 in mm:
                        for n1, n2 in lm:
                            if _parallel(m1, m2, n1, n2):
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
            while not valid and self.on_empty is not None and self.on_empty(i):
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
MELODY_ATTEMPTS = 4  # melody plans tried before giving up (host with/without doubling, next host...)


def generate(chords: list[ChordSpan], key: Key, *, seed: int = 1, ensemble: Ensemble | None = None,
             mode: str | None = None, rules: Rules | None = None, instruments: dict[str, Instrument] | None = None,
             approach: str = "A", settings: Settings | None = None,
             locked: Orchestration | None = None, locked_ids: frozenset[str] = frozenset(),
             variation: int = 0, avoid: Orchestration | None = None) -> Orchestration:
    """Orchestrate confirmed chords with one approach. Raises GenerationError if impossible.

    mode: "safe" or "moderate" sets the Character of every section (otherwise settings decide).
    locked / locked_ids: keep these parts of an earlier orchestration exactly and orchestrate around them.
    variation / avoid: "Regenerate" - a different seed variation, pushed away from the earlier result.
    With a melody, if its first plan (instrument and doubling) can't be voiced, the next plans are tried.
    """
    kw = dict(seed=seed, ensemble=ensemble, mode=mode, rules=rules, instruments=instruments, approach=approach,
              settings=settings, locked=locked, locked_ids=locked_ids, variation=variation, avoid=avoid)
    has_melody = settings is not None and bool(settings.melody)
    first = None
    for attempt in range(MELODY_ATTEMPTS if has_melody else 1):
        try:
            return _generate(chords, key, melody_attempt=attempt, **kw)
        except _NoMorePlans as exc:
            if first is None:
                raise GenerationError(str(exc)) from None
            break
        except GenerationError as exc:
            first = first or exc
    iid = settings.melody_instrument if has_melody else None
    if iid is not None and str(first).startswith("These chords can't be connected"):
        insts = instruments or builtin_instruments()
        if iid in insts and insts[iid].section == "choir":
            raise GenerationError(
                f"The rest of the choir can't sing around your melody in the {insts[iid].name} without "
                "breaking a choir rule (parallel unisons/octaves or a leap over an octave), usually because "
                "the choir bass can't go low enough. Try Character: Moderate for the choir (wider range), "
                "another melody instrument, or Melody: auto.") from None
    raise first


class _NoMorePlans(GenerationError):
    pass


def _generate(chords: list[ChordSpan], key: Key, *, seed: int = 1, ensemble: Ensemble | None = None,
              mode: str | None = None, rules: Rules | None = None, instruments: dict[str, Instrument] | None = None,
              approach: str = "A", settings: Settings | None = None,
              locked: Orchestration | None = None, locked_ids: frozenset[str] = frozenset(),
              variation: int = 0, avoid: Orchestration | None = None, melody_attempt: int = 0) -> Orchestration:
    if mode is not None and mode not in CHARACTERS:
        raise ValueError("mode must be safe or moderate")
    if not chords:
        raise GenerationError("There are no chords to orchestrate.")
    if approach not in APPROACH:
        raise ValueError(f"approach must be one of {APPROACHES}")
    rules = rules or builtin_rules()
    insts = instruments or builtin_instruments()
    settings = settings or Settings()
    if ensemble is not None:
        settings = replace(settings, ensemble=ensemble)
    if mode is not None:
        settings = replace(settings, character=mode, section_character=())
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
    fixed_lines: list[Line] = []
    fcells: dict[str, list[int | None]] = {}
    flabels: dict[str, list[str | None]] = {}
    ffigs: dict[str, list[Figure | None]] = {}
    info: dict = {}
    # the melody (SPEC §5 step 3): one instrument by register (plus an optional octave doubling)
    drop: set[str] = set()  # model lines replaced by the melody
    mel = None
    if settings.melody:
        mel = _melody_plan(ap, settings, ens, insts, spans, melody_attempt)
        if mel is not None:
            for ln in mel["lines"]:
                pos = next((k for k, x in enumerate(all_lines) if x.instrument == ln.instrument), len(all_lines))
                all_lines.insert(pos, ln)
            drop |= mel["drop"]
            info["melody"] = mel["text"]
    locked_ids = frozenset(lid for lid in locked_ids if locked is not None and lid in locked.cells
                           and any(ln.id == lid for ln in all_lines))
    # fixed parts: the kept voicing, locked parts, then the melody
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
            if ln.id in locked.figures:
                ffigs[ln.id] = list(locked.figures[ln.id])
    if mel is not None:
        for ln in mel["lines"]:
            if ln.id not in fcells:
                fixed_lines.append(ln)
                fcells[ln.id] = list(mel["cells"][ln.id])
                flabels[ln.id] = ["mel" if p is not None else None for p in fcells[ln.id]]
                ffigs[ln.id] = list(mel["figures"])
    model_lines = approach_lines(ap, ens, insts, exclude=set(fcells) | drop, keep=keep)
    extras: dict = {}
    if mel is not None:
        extras["mel_lo"] = list(mel["lo"])
    # the bass line (SPEC §5 step 2): a bass file, or moderate mode's independent line, doubled in octaves
    bass = _bass_plan(settings, model_lines, insts, spans, key)
    on_empty = None
    if bass is not None:
        for ln in bass["lines"]:
            fixed_lines.append(ln)
            fcells[ln.id] = list(bass["cells"][ln.id])
            flabels[ln.id] = ["B" if p is not None else None for p in fcells[ln.id]]
            ffigs[ln.id] = list(bass["figures"][ln.id])
        model_lines = [ln for ln in model_lines if ln.id not in fcells and ln.id not in bass["resting"]]
        extras["bass_pin"] = list(bass["pin"])
        extras["l5_optional"] = True
        info["bass"] = bass["kind"]
    fixed = _Fixed(fixed_lines, fcells, flabels, ffigs) if fixed_lines else None
    if bass is not None and bass["kind"] == "independent":
        flat: set[int] = set()

        def _hold(i: int) -> bool:  # passing tones make chord i impossible: hold the bass there
            if i in flat or not any(len(fixed.figures[ln.id][i] or ()) > 1 for ln in bass["lines"]):
                return False
            flat.add(i)
            for ln in bass["lines"]:
                f = fixed.figures[ln.id][i]
                fixed.figures[ln.id][i] = ((spans[i].start, spans[i].end, 0, f[0][3]),)
            fixed.forget()
            return True
        on_empty = _hold
    has_fixed = fixed is not None and any(fixed.at(i) for i in range(n))
    cells: dict[str, list[int | None]] = {ln.id: [None] * n for ln in all_lines}
    labels: dict[str, list[str | None]] = {ln.id: [None] * n for ln in all_lines}
    voicing: list[dict] = [{} for _ in range(n)]
    if model_lines:
        setup = _Setup(model_lines, insts, ap, need_bass=not has_fixed, settings=settings)
        prev = None
        if avoid is not None:  # the result being replaced and the earlier variations before it
            prev = [{ln.id: cells_[ln.id] for ln in model_lines if ln.id in cells_}
                    for cells_ in [avoid.cells] + list(avoid.meta.get("previous", []))]
        solver = _Solver(setup, spans, key, seed, rules, insts, settings, fixed, variation, prev, extras)
        solver.on_empty = on_empty
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
            "free": set(), "origin": None, "figures": dict(fixed.figures) if fixed is not None else {},
            "extras": extras, "info": info,
            "previous": ([avoid.cells] + list(avoid.meta.get("previous", [])))[:REGEN_MEMORY] if avoid else []}
    orch = _finish(approach, key, seed, spans, all_lines, cells, meta, settings, rules, insts)
    # problems only between your own inputs (kept voicing, locked parts, melody and bass file) are shown, not
    # discarded; everything the generator adds must be clean
    bad = _must_fix(orch.report, rules, set(fcells))
    if bad:  # should never happen: every rule is enforced above
        raise GenerationError("The generated result failed the rule checker, so it was discarded:\n"
                              + "\n".join(i.message for i in bad))
    return orch


# ---------------------------------------------------------------- melody and bass files
# Melody instrument, by approach (first one that is playing and fits the melody's register wins)
MELODY_HOSTS = {
    "A": ("horn", "violins_1", "clarinet", "english_horn", "violas", "oboe", "flute", "trumpet", "violins_2",
          "tenor_trombone", "choir_soprano", "choir_alto", "choir_tenor"),
    "B": ("violins_1", "horn", "flute", "trumpet", "oboe", "clarinet", "violins_2", "violas", "english_horn",
          "tenor_trombone", "choir_soprano", "choir_alto", "choir_tenor"),
    "C": ("flute", "violins_1", "trumpet", "oboe", "piccolo", "clarinet", "violins_2", "horn", "violas",
          "choir_soprano", "choir_alto", "choir_tenor"),
}
DOUBLE_HOSTS = {
    "up": ("flute", "piccolo", "violins_1", "oboe", "violins_2", "clarinet", "trumpet", "choir_soprano"),
    "down": ("violas", "horn", "cellos", "clarinet", "violins_2", "english_horn", "tenor_trombone", "bassoon",
             "bass_clarinet", "choir_tenor", "choir_alto"),
}
AUTO_DOUBLE = {"A": "down", "B": "up", "C": "up"}  # Auto: at Density 4-5 of the melody's section
EXPORT_CODE = {
    "piccolo": "Picc", "flute": "Fl", "oboe": "Ob", "english_horn": "EH", "clarinet": "Cl", "bass_clarinet": "BCl",
    "bassoon": "Bn", "contrabassoon": "Cbn", "horn": "Hn", "trumpet": "Tpt", "tenor_trombone": "Tbn",
    "bass_trombone": "BTbn", "tuba": "Tba", "violins_1": "Vln1", "violins_2": "Vln2", "violas": "Vla",
    "cellos": "Vc", "basses": "Cb", "choir_soprano": "ChS", "choir_alto": "ChA", "choir_tenor": "ChT",
    "choir_bass": "ChB",
}
MELODY_ID, DOUBLE_ID = "mel", "mel-8"
BASS_FILE_OCTAVES = {"btbn": (-12, 0)}  # SPEC §5 step 2: bass trombone on the lower octave when it fits


def _inst_text(name: str) -> str:
    """'Violins I' stays, 'French horn' -> 'French horn', 'Flute' -> 'flute'."""
    return name if name.split()[0] in ("Violins", "French", "English") else name[0].lower() + name[1:]


def clip_notes(notes, end: int) -> list[Note]:
    return [Note(n.pitch, n.start, min(n.end, end), n.velocity) for n in notes if n.start < end and n.end > n.start]


def _figures_from(notes: list[Note], spans: list[ChordSpan], fill: list[int | None] | None = None
                  ) -> tuple[list[int | None], list[Figure | None]]:
    """Cell pitch and figure per chord for a monophonic line. The cell is the note sounding at the chord's
    start (or the first one starting in it). With `fill` (bass), a silent chord start is filled with that
    pitch until the line's first note there."""
    cells, figs = [], []
    for i, span in enumerate(spans):
        inside = [n for n in notes if n.start < span.end and n.end > span.start]
        at = [n for n in inside if n.start <= span.start + TOLERANCE]
        rows = []
        if at:
            cell = at[0].pitch
        elif fill is not None and fill[i] is not None:
            cell = fill[i]
            first = min((n.start for n in inside), default=span.end)
            rows.append((span.start, first, 0, False))
        elif inside:
            cell = inside[0].pitch
        else:
            cells.append(None)
            figs.append(None)
            continue
        for nt in inside:
            s, e = max(nt.start, span.start), min(nt.end, span.end)
            if not rows and nt.start <= span.start + TOLERANCE:
                s = span.start  # a note struck a hair late still starts the chord
            if e > s:
                rows.append((s, e, nt.pitch - cell, nt.start < span.start))
        cells.append(cell)
        figs.append(tuple(sorted(rows)))
    return cells, figs


def _fits(notes, inst: Instrument, moderate: bool, shift: int = 0) -> bool:
    return all(inst.is_comfortable(n.pitch + shift) or (moderate and inst.is_playable(n.pitch + shift))
               for n in notes)


DOUBLE_DOWN_FLOOR = 55  # an octave-down doubling stays at G3 or above (clear of the bass register)


def _melody_plan(ap: Approach, settings: Settings, ens: Ensemble, insts, spans, attempt: int = 0) -> dict | None:
    """Which instrument plays the melody (and its octave doubling), and which model lines that replaces.
    attempt 0 is the first choice; attempt 1 drops the doubling, 2 takes the next instrument with its
    doubling, 3 the next instrument without. _NoMorePlans when there is no such plan."""
    end = spans[-1].end
    notes = clip_notes(settings.melody, end)
    if not notes:
        return None
    available = ensemble_lines(ens, insts)
    by_inst: dict[str, list[Line]] = {}
    for ln in available:
        by_inst.setdefault(ln.instrument, []).append(ln)
    leaps = max((abs(b.pitch - a.pitch) for a, b in zip(notes, notes[1:])), default=0)

    def eligible(iid: str) -> bool:
        """Playing, has an upper (harmony) line to give up, and a choir voice only without big leaps."""
        if iid not in by_inst or not any(ln.voices[0] in UPPER for ln in by_inst[iid]):
            return False
        if settings.keep is not None and insts[iid].section == "strings":
            return False  # keep-as-is: the strings play your voicing
        return insts[iid].section != "choir" or leaps <= 12

    def moderate(iid):
        return settings.character_for(insts[iid].section) == MODERATE

    if settings.melody_instrument is not None:
        iid = settings.melody_instrument
        if iid not in by_inst:
            raise _NoMorePlans(f"The melody instrument ({insts[iid].name if iid in insts else iid}) isn't playing.")
        hosts = [(iid, o) for o in (0, -12, 12, -24, 24) if _fits(notes, insts[iid], moderate(iid), o)][:1]
        if not hosts:
            raise _NoMorePlans(f"The melody doesn't fit the {insts[iid].name}'s range, even an octave away.")
    else:
        hosts = [(iid, o) for o in (0, -12, 12) for iid in MELODY_HOSTS[ap.id]
                 if eligible(iid) and _fits(notes, insts[iid], moderate(iid), o)]
        if not hosts:
            raise _NoMorePlans("No playing instrument can take the melody in its range. "
                               "Turn on violins, horns or flutes, or switch Character to Moderate.")
    if attempt // 2 >= len(hosts):
        raise _NoMorePlans("no more melody plans")
    host, shift = hosts[attempt // 2]
    hl = by_inst[host]
    top = max((ln for ln in hl if ln.voices[0] in UPPER), key=lambda ln: UPPER.index(ln.voices[0]), default=hl[0])
    lines = [Line(MELODY_ID, host, f"{insts[host].name} melody", f"{EXPORT_CODE[host]}-mel", (), role="melody",
                  forces=_ALL, program=top.program)]
    drop = {top.id}
    text = f"melody in the {_inst_text(insts[host].name)}" + (" (an octave down)" if shift < 0 else
                                                         " (an octave up)" if shift > 0 else "")
    direction = settings.melody_double
    if direction == "auto":
        direction = AUTO_DOUBLE[ap.id] if ens.density_for(insts[host].section) >= 4 else "off"
    if attempt % 2 == 1:
        if direction not in ("up", "down"):
            raise _NoMorePlans("no more melody plans")
        direction = "off"  # second try: without the doubling
    dshift = 0
    if direction in ("up", "down"):
        d = 12 if direction == "up" else -12
        low_ok = d > 0 or min(nt.pitch for nt in notes) + shift + d >= DOUBLE_DOWN_FLOOR
        dbl = next((iid for iid in DOUBLE_HOSTS[direction] if iid != host and eligible(iid) and low_ok
                    and _fits(notes, insts[iid], moderate(iid), shift + d)), None)
        if dbl is not None:
            dl = by_inst[dbl]
            dtop = max((ln for ln in dl if ln.voices[0] in UPPER), key=lambda ln: UPPER.index(ln.voices[0]),
                       default=dl[0])
            tag = "8va" if d > 0 else "8vb"
            lines.append(Line(DOUBLE_ID, dbl, f"{insts[dbl].name} melody {tag}", f"{EXPORT_CODE[dbl]}-mel{tag}", (),
                              role="melody", forces=_ALL, program=dtop.program))
            drop.add(dtop.id)
            dshift = d
            text += f", doubled an octave {direction} in the {_inst_text(insts[dbl].name)}"
    moved = [Note(nt.pitch + shift, nt.start, nt.end, nt.velocity) for nt in notes]
    cells, figs = _figures_from(moved, spans)
    out_cells = {MELODY_ID: cells}
    if len(lines) > 1:
        out_cells[DOUBLE_ID] = [None if c is None else c + dshift for c in cells]
    lo = []
    for span in spans:
        inside = [nt.pitch for nt in moved if nt.start < span.end and nt.end > span.start]
        lo.append(min(inside) if inside else None)
    return {"lines": lines, "drop": drop, "cells": out_cells, "figures": figs, "lo": lo, "text": text,
            "host": host}


def independent_bass(spans: list[ChordSpan], key: Key) -> list[Note]:
    """Moderate mode's independent bass (SPEC §5 step 2): the chord's bass note, moving by diatonic step toward
    the next chord's bass at the end of chords at least a half note long (at most two passing notes)."""
    scale = key.scale_pcs()
    tie = _ties(spans)
    prev = 45
    pitches = []
    for span in spans:
        cands = [p for p in range(36, 56) if p % 12 == span.label.bass]
        p = min(cands, key=lambda q: (abs(q - prev), q))
        while p > BASS_WINDOW[1]:
            p -= 12
        while p < BASS_WINDOW[0]:
            p += 12
        pitches.append(p)
        prev = p
    notes: list[Note] = []
    for i, span in enumerate(spans):
        p, length = pitches[i], span.end - span.start
        if i > 0 and tie[i - 1] and notes and notes[-1].pitch == p and notes[-1].end == span.start:
            start = notes.pop().start
        else:
            start = span.start
        nxt = pitches[i + 1] if i + 1 < len(spans) and not tie[i] else None
        steps = []
        if nxt is not None and length >= 2 * 480 and abs(nxt - p) > 2:
            up = nxt > p
            between = [q for q in (range(p + 1, nxt) if up else range(p - 1, nxt, -1)) if q % 12 in scale]
            steps = between[-2:]
        if not steps:
            notes.append(Note(p, start, span.end, 100))
            continue
        step = 480 if length >= 4 * 480 else 240
        first = span.end - step * len(steps)
        notes.append(Note(p, start, first, 100))
        for k, q in enumerate(steps):
            notes.append(Note(q, first + k * step, first + (k + 1) * step, 100))
    return notes


def _bass_plan(settings: Settings, model_lines: list[Line], insts, spans, key) -> dict | None:
    """The bass file (or the independent bass) for every model line on the bass voice except the choir bass:
    the line is moved by octaves to the bass voice's register, then each line plays it at its own octave."""
    carriers = [ln for ln in model_lines if ln.voices and ln.voices[0] == "B" and ln.id != CHOIR_BASS]
    if not carriers:
        return None
    if settings.bass:
        kind = "file"
        notes = clip_notes(settings.bass, spans[-1].end)
    elif settings.independent_bass and all(
            settings.character_for(insts[ln.instrument].section) == MODERATE for ln in carriers):
        kind = "independent"
        notes = independent_bass(spans, key)
    else:
        return None
    # the choir bass sings the line too (holding the chord's bass under passing notes would clash), unless
    # that would make it leap more than an octave: then it keeps singing the chord's bass note
    carriers += [ln for ln in model_lines if ln.id == CHOIR_BASS]
    if not notes:
        return None
    mid = (BASS_WINDOW[0] + BASS_WINDOW[1]) / 2

    def spread(k):
        ps = [nt.pitch + 12 * k for nt in notes]
        return sum(max(0, BASS_WINDOW[0] - p, p - BASS_WINDOW[1]) for p in ps), abs(sum(ps) / len(ps) - mid)

    k = min(range(-4, 5), key=spread)
    ref = [Note(nt.pitch + 12 * k, nt.start, nt.end, nt.velocity) for nt in notes]
    # a silent chord start is filled with the chord's bass note nearest the line
    fill, last = [], ref[0].pitch
    for span in spans:
        sounding = [nt.pitch for nt in ref if nt.start <= span.start + TOLERANCE and nt.end > span.start]
        if sounding:
            last = sounding[0]
            fill.append(None)
        else:
            cands = [p for p in range(last - 6, last + 7) if p % 12 == span.label.bass]
            fill.append(cands[0])
    pin, _ = _figures_from(ref, spans, fill)
    lines, cells, figs, resting = [], {}, {}, []
    for ln in carriers:
        moderate = settings.character_for(insts[ln.instrument].section) == MODERATE
        inst = insts[ln.instrument]

        def ok(q, inst=inst, moderate=moderate):
            return inst.is_comfortable(q) or (moderate and inst.is_playable(q))

        offs = BASS_FILE_OCTAVES.get(ln.id, ln.octaves)
        # the line's octave: the first of its octaves that fits at least 2/3 of the notes, else the one that
        # fits most. A line doubling an octave below (basses, tuba, contrabassoon) rests on the notes it can't
        # reach there, so it keeps the line's shape (v1.0, Sam); other lines move such a note by an octave.
        off = next((o for o in offs if sum(ok(nt.pitch + o) for nt in ref) * 3 >= 2 * len(ref)), None)
        if off is None:
            off = max(offs, key=lambda o: sum(ok(nt.pitch + o) for nt in ref))
        below = off < 0
        moved = []
        for nt in ref:
            q = nt.pitch + off
            if below:
                if ok(q):
                    moved.append(Note(q, nt.start, nt.end, nt.velocity))
                continue
            for d in (0, 12, -12, 24, -24):
                if ok(q + d):
                    q += d
                    break
            else:
                q = None
            if q is None:
                break
            moved.append(Note(q, nt.start, nt.end, nt.velocity))
        else:
            if below:
                lfill = [None if f is None or not ok(f + off) else f + off for f in fill]
            else:
                lfill = [None if f is None else next((f + off + d for d in (0, 12, -12) if ok(f + off + d)), None)
                         for f in fill]
            if moved and (below or all(f is not None or fill[i] is None for i, f in enumerate(lfill))):
                c, fg = _figures_from(moved, spans, lfill)
                seq = [c[i] + d for i in range(len(spans)) if c[i] is not None for _, _, d, _ in fg[i]]
                if ln.id != CHOIR_BASS or all(abs(b - a) <= 12 for a, b in zip(seq, seq[1:])):
                    lines.append(ln)
                    cells[ln.id], figs[ln.id] = c, fg
                    continue
        if ln.id != CHOIR_BASS:
            resting.append(ln.id)  # can't play the line: rests (the choir bass stays on the chord's bass)
    if not lines:
        return None
    return {"lines": lines, "cells": cells, "figures": figs, "pin": pin, "kind": kind, "resting": resting}


def _finish(approach, key, seed, spans, lines, cells, meta, settings: Settings, rules, insts,
            reason: str | None = None) -> Orchestration:
    rules = rules or builtin_rules()
    insts = insts or builtin_instruments()
    mode = settings.mode({insts[ln.instrument].section for ln in lines})
    parts = _render(lines, spans, cells, meta["labels"], settings, meta.get("figures") or {}, key, rules, insts,
                    mode)
    report = check(parts, spans, key, mode, rules=rules, instruments=insts)
    if reason is None:
        reason = _reason(APPROACH[approach], lines, cells, insts, settings, meta, spans, key)
    vel = settings.velocity
    return Orchestration(approach, reason, key, mode, seed, list(spans), list(lines), parts, cells, report,
                         vel, vel, meta)


# ---------------------------------------------------------------- rendering (patterns, figures)
def _alt_tone(pitch: int, label: ChordLabel, ok) -> int | None:
    """16ths alternating: the next chord tone at least a minor 3rd below (or above) that the part can play."""
    pcs = label.pcs()
    for q in list(range(pitch - 3, pitch - 13, -1)) + list(range(pitch + 3, pitch + 13)):
        if q % 12 in pcs and ok(q):
            return q
    return None


_WINDOW_CACHE: dict = {}
_WINDOW_CACHE_MAX = 40000


def _check_cached(parts: list[Part], spans: list[ChordSpan], key: Key, mode: str, rules: Rules, insts) -> Report:
    """check(..., inside=False) for the rendering's small windows (one or two chords), remembered by content:
    the same window comes back for every pattern alternative and every re-render of the same harmony."""
    k = (tuple(parts), tuple(spans), key, mode, id(rules), id(insts))
    rep = _WINDOW_CACHE.get(k)
    if rep is None:
        if len(_WINDOW_CACHE) >= _WINDOW_CACHE_MAX:
            _WINDOW_CACHE.clear()
        rep = _WINDOW_CACHE[k] = check(parts, spans, key, mode, rules=rules, instruments=insts, inside=False)
    return rep


def _window(parts: list[Part], i: int, notes_at) -> list[Part]:
    """Checker parts for chord i alone, with the given notes per part (empty parts left out)."""
    out = []
    for p in parts:
        ns = notes_at(p.id)
        if ns:
            da = (p.doubles_at[i],) if p.doubles_at is not None else None
            out.append(replace(p, notes=tuple(ns), doubles_at=da))
    return out


def _render(lines: list[Line], spans: list[ChordSpan], cells, labels, settings: Settings,
            figures: dict[str, list[Figure | None]], key: Key, rules: Rules, insts, mode: str) -> list[Part]:
    """Checker parts with their real notes: rhythm patterns (SPEC §5c, §14), the melody and bass files' rhythm,
    per-section velocity and re-strike every bar.

    Patterns are re-checked chord by chord against plain Sustain: where a pattern adds a rule problem at a
    chord (an error or a generator_must_pass warning that Sustain doesn't have there), that chord first loses
    its passing tones, then the parts named in the problem step down: a part in Hybrid or Scale steps plays its
    shape in chord tones, then it sustains; if no part is named, every patterned part steps down. A Hybrid or
    Scale steps part whose scale notes clash a minor 2nd with the melody also plays chord tones at that chord.
    Levels per part and chord: 3 pattern in its note mode + passing tones, 2 pattern in its note mode,
    1 pattern in chord tones, 0 Sustain.
    """
    n = len(spans)
    tie = _ties(spans)
    sec = {ln.id: insts[ln.instrument].section for ln in lines}
    vel = {ln.id: settings.velocity_for(sec[ln.id]) for ln in lines}
    want: dict[str, str] = {}
    for ln in lines:
        if ln.id in figures:
            continue  # the melody and bass-file lines keep the file's rhythm
        pt = settings.pattern_for(ln.id, sec[ln.id], ln.instrument)
        want[ln.id] = pt if pat.allowed(pt, sec[ln.id] == "choir") else pat.SUSTAIN
    patterned = [lid for lid, pt in want.items() if pt != pat.SUSTAIN]
    uniform = len(set(vel.values())) <= 1 and (not vel or next(iter(vel.values())) == settings.velocity)
    if not patterned and not figures and not settings.restrike_bars and uniform:
        return build_parts(lines, spans, cells, labels, settings.velocity, insts, tie)  # exactly Milestone 4
    by_id = {ln.id: ln for ln in lines}
    scale = key.scale_pcs()
    moderate = {lid for lid in by_id if settings.character_for(sec[lid]) == MODERATE}
    level = {lid: [3] * n for lid in patterned}
    lib = pat.library()
    nmode = {lid: settings.note_mode_for(sec[lid]) for lid in patterned}
    accent = {lid: settings.accent_for(lid, sec[lid]) for lid in patterned}
    # a part whose shape changes in chord tones (Hybrid/Scale steps on a pattern with a contour)
    shaped = {lid for lid in patterned if nmode[lid] != pat.CHORD_TONES and not lib[want[lid]].flat}
    chord_pcs = [sp.label.pcs() for sp in spans]
    scales = [pat.chord_scale(chord_pcs[i] | {spans[i].label.bass}, key) for i in range(n)]

    def ok_pitch(lid):
        inst = insts[by_id[lid].instrument]
        return lambda q: inst.is_comfortable(q) or (lid in moderate and inst.is_playable(q))
    oks = {lid: ok_pitch(lid) for lid in patterned}

    def effective(lid, i) -> str:
        if lid in figures:
            return "figure"
        if lid in level and level[lid][i] == 0:
            return pat.SUSTAIN
        return want[lid]

    def chord_notes(lid: str, i: int) -> list[Note]:
        p = cells[lid][i]
        if p is None:
            return []
        span, v = spans[i], vel[lid]
        if lid in figures:
            return figure_notes(p, figures[lid][i], span, v)
        pt = effective(lid, i)
        if pt == pat.SUSTAIN:
            return [Note(p, span.start, span.end, v)]
        spec = lib[pt]
        mapper = None
        if not spec.flat:
            m = nmode[lid] if level[lid][i] >= 2 else pat.CHORD_TONES
            mapper = pat.make_mapper(p, chord_pcs[i], scales[i], m, oks[lid], spec.min_step)
        passing = None
        if (level[lid][i] >= 3 and spec.passing and lid in moderate and sec[lid] != "choir"
                and i + 1 < n and not tie[i]):
            q = pat.passing_pitch(p, cells[lid][i + 1], scale)
            passing = q if q is not None and oks[lid](q) else None
        return pat.render(pt, p, span.start, span.end, v, passing=passing, mapper=mapper, grouping=accent[lid])

    base = build_parts(lines, spans, cells, labels, settings.velocity, insts, tie)
    if patterned:
        for i, span in enumerate(spans):
            here = [lid for lid in patterned if cells[lid][i] is not None]
            if not here:
                continue

            def sustain_at(lid, i=i):
                p = cells[lid][i]
                if p is None:
                    return []
                if lid in figures:
                    return figure_notes(p, figures[lid][i], spans[i], vel[lid])
                return [Note(p, spans[i].start, spans[i].end, vel[lid])]

            ref = _check_cached(_window(base, i, sustain_at), [span], key, mode, rules, insts)
            known = {x.message for x in ref.issues}
            while True:  # every round steps at least one part down, so this ends (at worst all Sustain)
                rep = _check_cached(_window(base, i, lambda lid: chord_notes(lid, i)), [span], key, mode, rules, insts)
                bad = [x for x in _must_fix(rep, rules) if x.message not in known]
                if not bad:
                    # Hybrid / Scale steps notes a minor 2nd from the melody: those parts use chord tones here
                    clash = {pid for x in rep.by_check("melody_clash") if x.message not in known for pid in x.parts
                             if pid in shaped and level[pid][i] >= 2}
                    if not clash:
                        break
                    for lid in clash:
                        level[lid][i] = 1
                    continue
                if any(level[lid][i] == 3 for lid in here):
                    for lid in here:
                        level[lid][i] = min(level[lid][i], 2)
                    continue
                named = {pid for x in bad for pid in x.parts if pid in level and level[pid][i] > 0}
                down = named or {lid for lid in here if level[lid][i] > 0}
                if not down:
                    break
                for lid in down:
                    level[lid][i] = 1 if (level[lid][i] == 2 and lid in shaped) else 0
        # passing tones change the note into the next chord: drop them where they add parallel 5ths/8ves
        for i in range(n - 1):
            here = [lid for lid in patterned if level[lid][i] == 3 and cells[lid][i] is not None]
            # only chords where a part really ends on a passing tone (otherwise both checks are the same)
            if not here or not any(want[lid] in pat.PASSING_PATTERNS and lid in moderate for lid in here):
                continue
            two = [spans[i], spans[i + 1]]

            def pair(parts=base, i=i):
                out = []
                for p in parts:
                    ns = chord_notes(p.id, i) + chord_notes(p.id, i + 1)
                    if ns:
                        da = (p.doubles_at[i], p.doubles_at[i + 1]) if p.doubles_at is not None else None
                        out.append(replace(p, notes=tuple(ns), doubles_at=da))
                return out

            with_pt = _check_cached(pair(), two, key, mode, rules, insts)
            n_with = len(with_pt.by_check("parallels")) + len(_must_fix(with_pt, rules))
            saved = {lid: level[lid][i] for lid in here}
            for lid in here:
                level[lid][i] = 2
            without = _check_cached(pair(), two, key, mode, rules, insts)
            if n_with <= len(without.by_check("parallels")) + len(_must_fix(without, rules)):
                for lid, v in saved.items():
                    level[lid][i] = v
    merged: dict[str, list[Note]] = {}
    for ln in lines:
        lid = ln.id
        out: list[Note] = []
        for i in range(n):
            ns = chord_notes(lid, i)
            if ns and out and i > 0 and out[-1].pitch == ns[0].pitch and out[-1].end == ns[0].start:
                if lid in figures:
                    fig = figures[lid][i]
                    join = bool(fig) and fig[0][3]
                else:
                    join = (tie[i - 1] and effective(lid, i) == pat.SUSTAIN
                            and effective(lid, i - 1) == pat.SUSTAIN)
                if join:
                    first = ns[0]
                    out[-1] = Note(first.pitch, out[-1].start, first.end, out[-1].velocity)
                    ns = ns[1:]
            out.extend(ns)
        if settings.restrike_bars and lid not in figures:
            out = pat.split_at_bars(out)
        merged[lid] = out
    return build_parts(lines, spans, cells, labels, settings.velocity, insts, tie, notes=merged)


def rerender(orch: Orchestration, settings: Settings, rules=None, instruments=None) -> Orchestration:
    """The same pitches with other render-only settings (dynamics, patterns, re-strike). Nothing is
    regenerated; the checker runs again."""
    rules = rules or builtin_rules()
    insts = instruments or builtin_instruments()
    meta = dict(orch.meta, settings=settings)
    new = _finish(orch.approach, orch.key, orch.seed, orch.chords, orch.lines, orch.cells, meta, settings, rules,
                  insts, reason=orch.reason)
    new.report.issues.extend(swap_leaps(new, rules, insts))
    return new


RENDER_ONLY = ("dynamics", "section_dynamics", "pattern", "section_patterns", "instrument_patterns", "part_patterns",
               "restrike_bars", "note_mode", "section_note_modes", "accent", "section_accents", "part_variants")


def swap_leaps(orch: Orchestration, rules=None, instruments=None) -> list[Issue]:
    """Leaps that swapped chords made bigger than they were before the swap (and at least
    rules.swap_leap_min semitones), on both sides of every swapped chord."""
    rules = rules or builtin_rules()
    sources = orch.sources
    if orch.meta.get("origin") is None or all(s == orch.approach for s in sources):
        return []
    base = orch.meta["origin"].cells
    swapped = {i for i, s in enumerate(sources) if s != orch.approach}
    edges = sorted({e for i in swapped for e in (i, i + 1) if 0 < e < len(orch.chords)})
    out = []
    for e in edges:
        for ln in orch.lines:
            a, b = orch.cells[ln.id][e - 1], orch.cells[ln.id][e]
            if a is None or b is None:
                continue
            new = abs(b - a)
            ba, bb = base.get(ln.id, [None] * len(orch.chords))[e - 1], base.get(ln.id, [None] * len(orch.chords))[e]
            old = abs(bb - ba) if ba is not None and bb is not None else 0
            if new >= rules.swap_leap_min and new > old:
                span = orch.chords[e]
                out.append(Issue("swap_leap", WARNING,
                                 f"{ln.label} leaps {new} semitones ({note_name(a, 'ableton', orch.key)} to "
                                 f"{note_name(b, 'ableton', orch.key)}) into {position_text(span.start)} "
                                 f"({span.label.symbol(orch.key)}) after the swap.",
                                 (ln.id,), e, span.start, (a, b)))
    return out


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


def with_dynamics(orch: Orchestration, dynamics: str, rules=None, instruments=None,
                  section_dynamics=()) -> Orchestration:
    """The same notes at another dynamic (velocity and CC1, optionally per section). Nothing is regenerated."""
    return rerender(orch, replace(orch.settings, dynamics=dynamics, section_dynamics=section_dynamics),
                    rules, instruments)


def _reason(ap: Approach, lines: list[Line], cells, insts, settings: Settings, meta: dict | None = None,
            spans=None, key: Key | None = None) -> str:
    """One line on what this alternative does, from what actually plays."""
    meta = meta or {}
    playing = {ln.id for ln in lines if any(p is not None for p in cells[ln.id])}
    inst_of = {ln.id: ln.instrument for ln in lines}
    secs = {insts[inst_of[lid]].section for lid in playing}
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
    info = meta.get("info") or {}
    if info.get("melody"):
        bits.append(info["melody"])
    if info.get("bass") == "file":
        bits.append("bass line from your file in octaves")
    elif info.get("bass") == "independent":
        bits.append("independent bass moving by step")
    if settings.mode() == MODERATE:
        colours = sum(any(p % 12 in colour_pcs(c.label, key) for k, p in v.items() if k in UPPER)
                      for v, c in zip(meta.get("voices") or [], spans or [])) if key is not None else 0
        bits.append(f"9th/sus/6th colour on {colours} chord{'s' * (colours != 1)}" if colours
                    else "moderate range")
    text = ", ".join(bits)
    return f"{ap.name}: {text[0].lower() + text[1:] if text else text}."
