"""Generator (SPEC §5), Milestone 3: safe mode, approach A (low and warm), sustained notes.

How it works
    1. Lines. The approach lists the lines it uses (one per instrument line; divisi lines are separate),
       each tied to an abstract *voice*:
          B   the bass (the chord's bass note: root or slash bass), doubled in octaves
          L5  an open 5th above the bass, for root-position chords that have a perfect 5th
          h1-h4  four upper harmony voices, low to high
       Per voice, the first active line in priority order (strings, brass, woodwinds, choir) is the
       *primary*; every other line on that voice doubles it (`Part.doubles`). Bass and L5 lines share
       the group "low" (low-brass power-chord texture), so their parallels are intended.
    2. Candidates. For each chord, every voicing of the bass and upper voices from the labelled chord
       tones (safe mode) is built, cheap rules prune it (defining tones, no doubled leading tone / 7th,
       ranges), and it is scored (register, spacing, doubling, horns in their heroic zone).
       Each surviving candidate is then run through the real rule checker on its own.
    3. Path. A seeded Viterbi search picks one candidate per chord with the lowest total of chord scores
       plus voice-leading costs (common tones held, small steps, smooth top voice, contrary motion,
       parallels penalised). Choir leaps over an octave and choir parallels are never allowed.
    4. Notes. Every part sustains for the chord's length; a note common to two consecutive identical
       chords is tied through.
    5. Check. The whole result is checked. It is returned only with no errors and no
       `generator_must_pass` warnings; otherwise GenerationError is raised (it is never shown flagged).

The same chords, key, sections and seed always give the same result.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field

from .analysis.chords import QUALITIES, ChordLabel
from .checker import ChordSpan, Part, Report, check, required_tones
from .instruments import SECTIONS, Instrument, instruments as builtin_instruments
from .midi_io import Note, position_text
from .rules import SAFE, Rules, rules as builtin_rules
from .theory import Key

VOICES = ("B", "L5", "h1", "h2", "h3", "h4")
UPPER = ("h1", "h2", "h3", "h4")
SECTION_PRIORITY = ("strings", "brass", "woodwinds", "choir")  # which section's line is the primary

# Dynamics before the Milestone 4 slider: mf (SPEC §6).
VELOCITY = 80
CC1 = 80

# Search sizes. KEEP valid candidates per chord go into the path search; more if no path is found.
KEEP = (40, 200)
MAX_CANDIDATES_CHECKED = 2500


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


# Approach A, "low and warm" (SPEC §5): dense low-mid chord led by horns and low strings,
# basses and low brass in octaves with open 5ths, upper woodwinds doubling at the unison (no piccolo).
# Listed in score order.
LINES_A: tuple[Line, ...] = (
    Line("fl1", "flute", "Flute 1", "Fl1", ("h4",), role="high_harmony"),
    Line("fl2", "flute", "Flute 2", "Fl2", ("h3",), role="high_harmony"),
    Line("ob1", "oboe", "Oboe 1", "Ob1", ("h4",), role="high_harmony"),
    Line("ob2", "oboe", "Oboe 2", "Ob2", ("h3",), role="high_harmony"),
    Line("eh", "english_horn", "English horn", "EH", ("h2",)),
    Line("cl1", "clarinet", "Clarinet 1", "Cl1", ("h3",), role="high_harmony"),
    Line("cl2", "clarinet", "Clarinet 2", "Cl2", ("h2",)),
    Line("bcl", "bass_clarinet", "Bass clarinet", "BCl", ("h1",), role="low_harmony"),
    Line("bn1", "bassoon", "Bassoon 1", "Bn1", ("L5",), role="low_harmony"),
    Line("bn2", "bassoon", "Bassoon 2", "Bn2", ("B",), (0, 12), role="bass"),
    Line("cbn", "contrabassoon", "Contrabassoon", "Cbn", ("B",), (-12, 0), role="bass"),
    Line("hn1", "horn", "Horn 1", "Hn1", ("h4",), role="high_harmony"),
    Line("hn2", "horn", "Horn 2", "Hn2", ("h3",), role="high_harmony"),
    Line("hn3", "horn", "Horn 3", "Hn3", ("h2",)),
    Line("hn4", "horn", "Horn 4", "Hn4", ("h1",), role="low_harmony"),
    Line("tpt1", "trumpet", "Trumpet 1", "Tpt1", ("h4",), role="high_harmony"),
    Line("tpt2", "trumpet", "Trumpet 2", "Tpt2", ("h3",), role="high_harmony"),
    Line("tbn1", "tenor_trombone", "Trombone 1", "Tbn1", ("h1",), role="low_harmony"),
    Line("tbn2", "tenor_trombone", "Trombone 2", "Tbn2", ("L5",), role="low_harmony"),
    Line("btbn", "bass_trombone", "Bass trombone", "BTbn", ("B",), role="bass"),
    Line("tba", "tuba", "Tuba", "Tba", ("B",), (-12, 0), role="bass"),
    Line("vln1-a", "violins_1", "Violins I a", "Vln1-a", ("h4",), role="high_harmony"),
    Line("vln1-b", "violins_1", "Violins I b", "Vln1-b", ("h3",), role="high_harmony"),
    Line("vln2", "violins_2", "Violins II", "Vln2", ("h2",)),
    Line("vla", "violas", "Violas", "Vla", ("h1",), role="low_harmony"),
    Line("vc", "cellos", "Cellos", "Vc", ("B",), role="bass"),
    Line("cb", "basses", "Basses", "Cb", ("B",), (-12, 0), role="bass"),
    Line("ch-s", "choir_soprano", "Choir soprano", "ChS", ("h4",), role="high_harmony"),
    Line("ch-a", "choir_alto", "Choir alto", "ChA", ("h3",)),
    Line("ch-t", "choir_tenor", "Choir tenor", "ChT", ("h2",)),
    Line("ch-b", "choir_bass", "Choir bass", "ChB", ("B",), role="bass"),  # octave chosen per chord
)
CHOIR_BASS = "ch-b"
CHOIR_LINES = {"h4": "ch-s", "h3": "ch-a", "h2": "ch-t", "B": CHOIR_BASS}

# Pitch windows (MIDI, scientific C4 = 60).
BASS_WINDOW = (40, 51)  # the bass voice (cellos): E2..Eb3, one octave so octave doublings stay fixed
UPPER_WINDOW = (48, 77)  # C3..F5
# Approach A targets: low-mid density.
A_CENTER = 60.0  # mean of the upper voices
A_SPAN = 14  # upper voices within about a 9th
A_BASS = (40, 47)  # E2..B2 for the bass voice
HEROIC = (53, 65)  # horn F3..F4
PARALLEL_COST = 8.0  # parallel 5ths/8ves between independent lines (a checker warning): avoided when possible


@dataclass(frozen=True)
class Ensemble:
    """Which sections play (Milestone 3: section on/off toggles; presets come in Milestone 4)."""
    sections: frozenset[str] = frozenset(SECTIONS)

    def __post_init__(self):
        bad = set(self.sections) - set(SECTIONS)
        if bad:
            raise ValueError(f"unknown section(s) {sorted(bad)}")
        if not self.sections:
            raise ValueError("at least one section must play")


@dataclass(frozen=True)
class _Cand:
    """One chord's voicing: abstract voices plus the actual pitch of every line (None = rests)."""
    voices: tuple[tuple[str, int], ...]  # (voice, pitch) for sounding voices
    pitches: tuple[tuple[str, int | None], ...]  # (line id, pitch) for every active line
    cost: float

    def v(self, name: str) -> int | None:
        return dict(self.voices).get(name)

    def p(self, line_id: str) -> int | None:
        return dict(self.pitches).get(line_id)

    @property
    def key(self):
        return self.pitches


@dataclass
class Orchestration:
    """A finished, checked orchestration (one alternative)."""
    approach: str
    reason: str
    key: Key
    mode: str
    seed: int
    chords: list[ChordSpan]
    lines: list[Line]  # active lines, score order
    parts: list[Part]  # same order as lines
    cells: dict[str, list[int | None]]  # line id -> pitch per chord (None = rest)
    report: Report
    velocity: int = VELOCITY
    cc1: int = CC1
    meta: dict = field(default_factory=dict)

    def part(self, line_id: str) -> Part:
        return next(p for p in self.parts if p.id == line_id)

    def line(self, line_id: str) -> Line:
        return next(ln for ln in self.lines if ln.id == line_id)


# ---------------------------------------------------------------- setup
class _Setup:
    def __init__(self, ensemble: Ensemble, insts: dict[str, Instrument]):
        self.inst = insts
        self.lines = [ln for ln in LINES_A if insts[ln.instrument].section in ensemble.sections]
        if not self.lines:
            raise GenerationError("No instruments are active.")
        self.choir = any(ln.id == CHOIR_BASS for ln in self.lines)
        rank = {s: i for i, s in enumerate(SECTION_PRIORITY)}
        order = {ln.id: i for i, ln in enumerate(self.lines)}
        self.primary: dict[str, str] = {}
        for v in VOICES:
            carriers = [ln for ln in self.lines if ln.voices[0] == v]
            if carriers:
                best = min(carriers, key=lambda ln: (rank[insts[ln.instrument].section], order[ln.id]))
                self.primary[v] = best.id
        self.upper = [v for v in UPPER if v in self.primary or any(v in ln.voices for ln in self.lines)]
        self.low_ids = [ln.id for ln in self.lines if ln.voices[0] in ("B", "L5")]
        if "B" not in self.primary:
            raise GenerationError("Nothing can play the bass line with these sections.")

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
                   rng: random.Random) -> float:
    ups = [voices[v] for v in UPPER if v in voices]
    cost = 0.0
    if ups:
        cost += 0.15 * abs(sum(ups) / len(ups) - A_CENTER)
        cost += 0.25 * max(0, max(ups) - min(ups) - A_SPAN)
        for a, b in zip(ups, ups[1:]):
            cost += 0.3 * max(0, b - a - 7) + (1.0 if a == b else 0.0)
    b = voices["B"]
    cost += 0.2 * max(0, A_BASS[0] - b, b - A_BASS[1])
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
    return cost + rng.random() * 0.25


def _candidates(setup: _Setup, span: ChordSpan, key: Key, seed: int, index: int) -> list[_Cand]:
    label = span.label
    chord_pcs = label.pcs()
    sens = _sensitive_pcs(label, key)
    need = set(required_tones(label))
    ivs = QUALITIES[label.quality][0]
    root_pos = label.bass == label.root
    want_l5 = root_pos and 7 in ivs and any("L5" in ln.voices for ln in setup.lines)
    rng = random.Random(f"{seed}:{index}:{label.root}:{label.quality}:{label.bass}")
    lo, hi = UPPER_WINDOW
    tones = [p for p in range(lo, hi + 1) if p % 12 in chord_pcs]
    n_up = len(setup.upper)
    choir_ranges = {}
    if setup.choir:
        for v, lid in CHOIR_LINES.items():
            if v != "B" and v in setup.upper:
                choir_ranges[v] = setup.inst[next(ln.instrument for ln in setup.lines if ln.id == lid)].comfortable
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
            if ups[0] <= bass:
                continue
            voices = {"B": bass}
            for v, p in zip(setup.upper, ups):
                voices[v] = p
            if want_l5 and bass + 7 < ups[0]:
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
                tenor = voices.get("h2", 127)
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
                cost = _vertical_cost(setup, label, voices, pitches, rng)
                out.append(_Cand(tuple(sorted(voices.items())), tuple(pitches.items()), cost))
    out.sort(key=lambda c: c.cost)
    return out


def _parts_for(setup: _Setup, cands: list[_Cand], spans: list[ChordSpan], tie: list[bool]) -> list[Part]:
    """Checker parts for a run of chords. tie[i]: chord i+1 repeats chord i (hold common notes)."""
    parts = []
    for ln in setup.lines:
        notes: list[Note] = []
        for i, (c, s) in enumerate(zip(cands, spans)):
            p = c.p(ln.id)
            if p is None:
                continue
            if i > 0 and tie[i - 1] and notes and notes[-1].pitch == p and notes[-1].end == s.start:
                notes[-1] = Note(p, notes[-1].start, s.end, VELOCITY)
            else:
                notes.append(Note(p, s.start, s.end, VELOCITY))
        primary = setup.primary.get(ln.voices[0])
        doubles = primary if primary and primary != ln.id else None
        group = "low" if ln.voices[0] in ("B", "L5") else None
        parts.append(Part(ln.id, ln.instrument, tuple(notes), ln.role, doubles, group, ln.label))
    return parts


def _must_fix(report: Report, rules: Rules) -> list:
    return [i for i in report.issues
            if i.severity == "error" or rules.checks[i.check].generator_must_pass]


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


def _transition(setup: _Setup, a: _Cand, b: _Cand, same_chord: bool) -> float | None:
    """Cost of moving from voicing a to b, or None if it breaks a hard rule."""
    if same_chord:
        return 0.0 if a.key == b.key else 50.0
    # choir: leaps of at most an octave, no parallels between any two choir voices (hard rules)
    if setup.choir:
        ch = [lid for lid in ("ch-s", "ch-a", "ch-t", CHOIR_BASS) if a.p(lid) is not None and b.p(lid) is not None]
        for lid in ch:
            if abs(b.p(lid) - a.p(lid)) > 12:
                return None
        for x, y in itertools.combinations(ch, 2):
            if _parallel(a.p(x), b.p(x), a.p(y), b.p(y)):
                return None
    av, bv = dict(a.voices), dict(b.voices)
    cost = 0.0
    for v in UPPER:
        if v in av and v in bv:
            d = abs(bv[v] - av[v])
            if d:
                cost += 0.5 + 0.25 * d + 0.5 * max(0, d - 5) + 4.0 * max(0, d - 12)
    if "h4" in av and "h4" in bv:
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
            cost += PARALLEL_COST
    # the low group's real lines (some switch octave or switch between the open 5th and h1)
    pa, pb = dict(a.pitches), dict(b.pitches)
    motions = {(pa[i], pb[i]) for i in setup.low_ids if pa.get(i) is not None and pb.get(i) is not None}
    for x in ups:
        for m1, m2 in motions:
            if _parallel(av[x], bv[x], m1, m2):
                cost += PARALLEL_COST
    return cost


# ---------------------------------------------------------------- public
def generate(chords: list[ChordSpan], key: Key, *, seed: int = 1, ensemble: Ensemble | None = None,
             mode: str = SAFE, rules: Rules | None = None,
             instruments: dict[str, Instrument] | None = None) -> Orchestration:
    """Orchestrate confirmed chords (approach A, safe mode). Raises GenerationError if impossible."""
    if mode != SAFE:
        raise ValueError("Milestone 3 generates in safe mode only.")
    if not chords:
        raise GenerationError("There are no chords to orchestrate.")
    rules = rules or builtin_rules()
    insts = instruments or builtin_instruments()
    setup = _Setup(ensemble or Ensemble(), insts)
    spans = sorted(chords, key=lambda c: c.start)
    same = [spans[i].label == spans[i + 1].label and spans[i].end == spans[i + 1].start
            for i in range(len(spans) - 1)]

    # candidates per chord, each checked on its own by the real checker
    all_valid: list[list[_Cand]] = []
    for i, span in enumerate(spans):
        valid = []
        for c in _candidates(setup, span, key, seed, i)[:MAX_CANDIDATES_CHECKED]:
            rep = check(_parts_for(setup, [c], [span], []), [span], key, SAFE, rules=rules, instruments=insts)
            if not _must_fix(rep, rules):
                valid.append(c)
                if len(valid) >= KEEP[-1]:
                    break
        if not valid:
            raise GenerationError(
                f"No voicing of {span.label.symbol(key)} at {position_text(span.start)} passes the rules "
                "with the sections that are on. Try turning another section on.")
        all_valid.append(valid)

    for keep in KEEP:
        path = _viterbi(setup, [v[:keep] for v in all_valid], same)
        if path is not None:
            break
    else:
        raise GenerationError("These chords can't be connected without breaking a choir rule "
                              "(a leap over an octave or parallel 5ths/octaves). Try turning the choir off.")

    parts = _parts_for(setup, path, spans, same)
    report = check(parts, spans, key, SAFE, rules=rules, instruments=insts)
    bad = _must_fix(report, rules)
    if bad:  # should never happen: every rule is enforced above
        raise GenerationError("The generated result failed the rule checker, so it was discarded:\n"
                              + "\n".join(i.message for i in bad))
    cells = {ln.id: [c.p(ln.id) for c in path] for ln in setup.lines}
    return Orchestration("A", _reason(setup), key, SAFE, seed, spans, list(setup.lines), parts, cells, report,
                         meta={"voices": [dict(c.voices) for c in path]})


def _viterbi(setup: _Setup, layers: list[list[_Cand]], same: list[bool]) -> list[_Cand] | None:
    best = [c.cost for c in layers[0]]
    back: list[list[int]] = []
    for i in range(1, len(layers)):
        cur, ptr = [], []
        for b in layers[i]:
            top, arg = None, -1
            for j, a in enumerate(layers[i - 1]):
                if best[j] is None:
                    continue
                t = _transition(setup, a, b, same[i - 1])
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


def _reason(setup: _Setup) -> str:
    secs = {setup.inst[ln.instrument].section for ln in setup.lines}
    bits = []
    if "strings" in secs and "brass" in secs:
        bits.append("close mid-register chord in strings and horns")
    elif "strings" in secs:
        bits.append("close mid-register chord in the strings")
    elif "brass" in secs:
        bits.append("close mid-register chord in the horns")
    else:
        bits.append("close mid-register chord")
    if any(ln.voices[0] == "L5" for ln in setup.lines):
        bits.append("low brass and bassoons in open 5ths over the bass")
    if "strings" in secs:
        bits.append("basses an octave under the cellos")
    if "woodwinds" in secs:
        bits.append("woodwinds doubling at the unison")
    if setup.choir:
        bits.append("choir in four parts")
    return "Low and warm: " + ", ".join(bits) + "."
