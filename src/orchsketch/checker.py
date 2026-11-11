"""Rule checker (SPEC §5a, §7). Pure Python: works on plain note lists, no UI.

Input
    parts   - one `Part` per line of music (a divisi line is its own part). Melodic checks
              (leaps, parallels) follow each part's top note.
    chords  - the confirmed chord labels with their positions (`ChordSpan`).
    key     - the key the user entered.
    mode    - "safe" or "moderate". In safe mode a note outside comfortable range is an error.

Output
    a `Report` listing every `Issue` by check, part and chord.

Two parts are *linked* (not independent) when one doubles the other (`Part.doubles`, followed
through chains) or when they share a `Part.group` (e.g. low brass in open-5th power chords).
Linked parts may move in parallel 5ths/8ves and don't count as doubling each other.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .analysis.chords import QUALITIES, ChordLabel
from .instruments import ROLES, Instrument, instruments as builtin_instruments
from .midi_io import Note, position_text
from .rules import ERROR, SAFE, WARNING, Rules, rules as builtin_rules
from .theory import Key, note_name


# ---------------------------------------------------------------- input / output types
@dataclass(frozen=True)
class Part:
    id: str  # unique, e.g. "vln1-a"
    instrument: str  # instrument id, e.g. "violins_1"
    notes: tuple[Note, ...]
    role: str | None = None  # one of instruments.ROLES
    doubles: str | None = None  # id of the part this part doubles at the unison/octave
    group: str | None = None  # parts with the same group move together on purpose
    name: str = ""  # display name; defaults to the instrument name

    def __post_init__(self):
        object.__setattr__(self, "notes", tuple(sorted(self.notes, key=lambda n: (n.start, -n.pitch))))
        if self.role is not None and self.role not in ROLES:
            raise ValueError(f"part {self.id}: unknown role {self.role!r}")


@dataclass(frozen=True)
class ChordSpan:
    start: int
    end: int
    label: ChordLabel


@dataclass(frozen=True)
class Issue:
    check: str  # rules.CHECK_IDS
    severity: str  # "error" / "warning"
    message: str
    parts: tuple[str, ...] = ()
    chord: int | None = None  # index into the chords list
    tick: int | None = None
    pitches: tuple[int, ...] = ()


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == WARNING]

    @property
    def ok(self) -> bool:
        """No errors (warnings are allowed)."""
        return not self.errors

    def by_check(self, check: str) -> list[Issue]:
        return [i for i in self.issues if i.check == check]

    def for_part(self, part_id: str) -> list[Issue]:
        return [i for i in self.issues if part_id in i.parts]

    def for_chord(self, chord: int) -> list[Issue]:
        return [i for i in self.issues if i.chord == chord]

    def summary(self) -> str:
        e, w = len(self.errors), len(self.warnings)
        if not self.issues:
            return "Checker: no problems."
        return f"Checker: {e} error{'s' * (e != 1)}, {w} warning{'s' * (w != 1)}."

    def text(self) -> str:
        lines = [self.summary()]
        for i in sorted(self.issues, key=lambda i: (i.severity != ERROR, i.tick or 0, i.check)):
            lines.append(f"  [{i.severity.upper():7}] {i.message}")
        return "\n".join(lines)


def chords_from_session(session) -> list[ChordSpan]:
    """Chord spans from an AnalysisSession. Every chord must be confirmed first."""
    spans = []
    for r in session.chord_results:
        label = session.confirmed_label(r.segment.index)
        if label is None:
            raise ValueError(f"The chord at {position_text(r.segment.start)} isn't confirmed yet.")
        spans.append(ChordSpan(r.segment.start, r.segment.end, label))
    return spans


# ---------------------------------------------------------------- helpers
_DEGREE = {0: "root", 1: "b9th", 2: "9th", 3: "3rd", 4: "3rd", 5: "4th", 6: "5th", 7: "5th",
           8: "5th", 9: "6th", 10: "7th", 11: "7th"}


def required_tones(label: ChordLabel) -> dict[int, str]:
    """Pitch class -> tone name that must sound somewhere for this chord (SPEC §5a, M2 decision).

    Every template tone is required, except the 5th of the chords the labeller lets drop it
    (maj, m, 7, maj7, m7, add9, 9, m9). A slash bass outside the chord is required too.
    """
    ivs, omit5, _ = QUALITIES[label.quality]
    out: dict[int, str] = {}
    for iv in ivs:
        if omit5 and iv == 7:
            continue
        name = _DEGREE[iv]
        if label.quality == "sus2" and iv == 2:
            name = "2nd"
        elif label.quality == "dim7" and iv == 9:
            name = "7th"
        out[(label.root + iv) % 12] = name
    if label.bass not in label.pcs():
        out.setdefault(label.bass, "bass note")
    return out


def _seventh_pcs(label: ChordLabel) -> set[int]:
    ivs = QUALITIES[label.quality][0]
    if label.quality == "dim7":
        return {(label.root + 9) % 12}
    return {(label.root + iv) % 12 for iv in ivs if iv in (10, 11)}


class _Links:
    """Union-find over part ids: doubling chains and shared groups."""

    def __init__(self, parts: list[Part]):
        self.parent = {p.id: p.id for p in parts}
        by_group: dict[str, str] = {}
        for p in parts:
            if p.doubles is not None:
                if p.doubles not in self.parent:
                    raise ValueError(f"part {p.id} doubles unknown part {p.doubles!r}")
                self._union(p.id, p.doubles)
            if p.group:
                if p.group in by_group:
                    self._union(p.id, by_group[p.group])
                else:
                    by_group[p.group] = p.id

    def _find(self, a: str) -> str:
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def _union(self, a: str, b: str):
        self.parent[self._find(a)] = self._find(b)

    def linked(self, a: str, b: str) -> bool:
        return self._find(a) == self._find(b)


class _Checker:
    def __init__(self, parts, chords, key, mode, rules, insts, style):
        ids = [p.id for p in parts]
        if len(set(ids)) != len(ids):
            raise ValueError("part ids must be unique")
        for p in parts:
            if p.instrument not in insts:
                raise ValueError(f"part {p.id}: unknown instrument {p.instrument!r}")
        self.parts: list[Part] = list(parts)
        self.by_id = {p.id: p for p in parts}
        self.chords: list[ChordSpan] = sorted(chords, key=lambda c: c.start)
        self.key: Key = key
        self.mode = mode
        self.rules: Rules = rules
        self.inst: dict[str, Instrument] = insts
        self.style = style
        self.links = _Links(self.parts)
        self.issues: list[Issue] = []
        self._seen: set = set()

    # --- naming / bookkeeping
    def pname(self, pid: str) -> str:
        p = self.by_id[pid]
        return p.name or self.inst[p.instrument].name

    def n(self, pitch: int) -> str:
        return note_name(pitch, self.style, self.key)

    def chord_at(self, tick: int) -> int | None:
        for i, c in enumerate(self.chords):
            if c.start <= tick < c.end:
                return i
        return None

    def where(self, tick: int, chord: int | None) -> str:
        pos = position_text(tick)
        if chord is None:
            return pos
        return f"{pos} ({self.chords[chord].label.symbol(self.key)})"

    def add(self, check, message, parts=(), chord=None, tick=None, pitches=(), dedupe=None):
        if dedupe is not None:
            k = (check, dedupe)
            if k in self._seen:
                return
            self._seen.add(k)
        self.issues.append(Issue(check, self.rules.severity(check, self.mode), message,
                                 tuple(parts), chord, tick, tuple(pitches)))

    def slices(self):
        """(tick, [(part, pitch), ...]) for every span where the sounding notes don't change."""
        bounds = {c.start for c in self.chords}
        for p in self.parts:
            for nt in p.notes:
                bounds.update((nt.start, nt.end))
        out = []
        for t in sorted(bounds):
            sounding = [(p, nt.pitch) for p in self.parts for nt in p.notes if nt.start <= t < nt.end]
            if sounding:
                out.append((t, sounding))
        return out

    @staticmethod
    def _by_pitch(sounding):
        d: dict[int, list[Part]] = defaultdict(list)
        for p, pitch in sounding:
            d[pitch].append(p)
        return d

    # --- line helpers (top note per part)
    @staticmethod
    def _top_at_start(part: Part, span: ChordSpan) -> int | None:
        notes = [n for n in part.notes if n.start < span.end and n.end > span.start]
        if not notes:
            return None
        first = min(n.start for n in notes)
        return max(n.pitch for n in notes if n.start == first)

    @staticmethod
    def _top_at_end(part: Part, span: ChordSpan) -> int | None:
        notes = [n for n in part.notes if n.start < span.end and n.end > span.start]
        if not notes:
            return None
        last = max(n.start for n in notes)
        return max(n.pitch for n in notes if n.start == last)

    @staticmethod
    def _line(part: Part) -> list[tuple[int, int]]:
        tops: dict[int, int] = {}
        for n in part.notes:
            tops[n.start] = max(tops.get(n.start, -1), n.pitch)
        return sorted(tops.items())

    # --- checks
    def check_ranges(self):
        for p in self.parts:
            inst = self.inst[p.instrument]
            for nt in p.notes:
                c = self.chord_at(nt.start)
                if not inst.is_playable(nt.pitch):
                    self.add("playable_range",
                             f"{self.pname(p.id)}: {self.n(nt.pitch)} at {self.where(nt.start, c)} is outside "
                             f"the playable range {inst.range_text('playable', self.style)}.",
                             [p.id], c, nt.start, [nt.pitch], dedupe=(p.id, c, nt.pitch))
                elif not inst.is_comfortable(nt.pitch):
                    self.add("comfortable_range",
                             f"{self.pname(p.id)}: {self.n(nt.pitch)} at {self.where(nt.start, c)} is outside "
                             f"the comfortable range {inst.range_text('comfortable', self.style)}.",
                             [p.id], c, nt.start, [nt.pitch], dedupe=(p.id, c, nt.pitch))

    def check_defining_tones(self):
        for i, span in enumerate(self.chords):
            notes = [(p, nt) for p in self.parts for nt in p.notes if nt.start < span.end and nt.end > span.start]
            sym = span.label.symbol(self.key)
            if not notes:
                self.add("defining_tone", f"{sym} at {position_text(span.start)}: nothing sounds.",
                         chord=i, tick=span.start)
                continue
            present = {nt.pitch % 12 for _, nt in notes}
            for pc, tone in required_tones(span.label).items():
                if pc not in present:
                    self.add("defining_tone",
                             f"{sym} at {position_text(span.start)}: the {tone} ({self.key.pc_name(pc)}) is missing.",
                             chord=i, tick=span.start)

    def check_vertical(self, slices):
        lil_names = self.rules.interval_names
        choir_rank = {iid: k for k, iid in enumerate(self.rules.choir_order)}
        part_rank = {p.id: k for k, p in enumerate(self.parts)}
        for t, sounding in slices:
            c = self.chord_at(t)
            by_pitch = self._by_pitch(sounding)
            # low-interval limits, whole texture
            pitches = sorted(by_pitch)
            for lo, hi in zip(pitches, pitches[1:]):
                d = hi - lo
                limit = self.rules.low_limit(d)
                if limit is not None and lo < limit:
                    ps = sorted({p.id for p in by_pitch[lo] + by_pitch[hi]})
                    self.add("low_interval",
                             f"{self.n(lo)}–{self.n(hi)} ({lil_names.get(d, f'{d} semitones')}) at "
                             f"{self.where(t, c)} is below the low-interval limit; its lower note must be "
                             f"{self.n(limit)} or higher.",
                             ps, c, t, [lo, hi], dedupe=(c, lo, hi))
            # spacing, per section
            sections: dict[str, dict[int, list[Part]]] = defaultdict(lambda: defaultdict(list))
            for p, pitch in sounding:
                sections[self.inst[p.instrument].section][pitch].append(p)
            for sec, sp in sections.items():
                sp_pitches = sorted(sp)
                for lo, hi in zip(sp_pitches, sp_pitches[1:]):
                    if hi - lo <= self.rules.spacing_max:
                        continue
                    if lo == sp_pitches[0] or any(p.role == "bass" for p in sp[lo]):
                        continue  # a wide gap above the bass is allowed
                    ps = sorted({p.id for p in sp[lo] + sp[hi]})
                    self.add("spacing",
                             f"{sec.capitalize()}: {self.n(lo)} and {self.n(hi)} at {self.where(t, c)} are "
                             f"{hi - lo} semitones apart (more than an octave between upper voices).",
                             ps, c, t, [lo, hi], dedupe=(c, sec, lo, hi))
            # choir crossing
            choir = [(p, pitch) for p, pitch in sounding if self.inst[p.instrument].section == "choir"]
            by_part: dict[str, list[int]] = defaultdict(list)
            for p, pitch in choir:
                by_part[p.id].append(pitch)
            order = sorted(by_part, key=lambda pid: (choir_rank.get(self.by_id[pid].instrument, 99), part_rank[pid]))
            for a in range(len(order)):
                for b in range(a + 1, len(order)):
                    upper, lower = order[a], order[b]
                    if max(by_part[lower]) > min(by_part[upper]):
                        self.add("choir_crossing",
                                 f"{self.pname(lower)} ({self.n(max(by_part[lower]))}) is above "
                                 f"{self.pname(upper)} ({self.n(min(by_part[upper]))}) at {self.where(t, c)}: choir voices crossing.",
                                 [upper, lower], c, t, [max(by_part[lower]), min(by_part[upper])],
                                 dedupe=(c, upper, lower))

    def check_choir_leaps(self):
        for p in self.parts:
            if self.inst[p.instrument].section != "choir":
                continue
            line = self._line(p)
            for (t1, a), (t2, b) in zip(line, line[1:]):
                if abs(b - a) > self.rules.choir_max_leap:
                    c = self.chord_at(t2)
                    self.add("choir_leap",
                             f"{self.pname(p.id)} leaps {abs(b - a)} semitones ({self.n(a)} to {self.n(b)}) "
                             f"at {self.where(t2, c)}; choir voices move at most an octave.",
                             [p.id], c, t2, [a, b])

    def check_parallels(self):
        for i in range(len(self.chords) - 1):
            s1, s2 = self.chords[i], self.chords[i + 1]
            lines = {}
            for p in self.parts:
                a, b = self._top_at_end(p, s1), self._top_at_start(p, s2)
                if a is not None and b is not None and a != b:
                    lines[p.id] = (a, b)
            ids = [p.id for p in self.parts if p.id in lines]
            for x in range(len(ids)):
                for y in range(x + 1, len(ids)):
                    pa, pb = ids[x], ids[y]
                    (a1, a2), (b1, b2) = lines[pa], lines[pb]
                    if (a2 - a1 > 0) != (b2 - b1 > 0):
                        continue  # contrary motion
                    iv1, iv2 = abs(a1 - b1) % 12, abs(a2 - b2) % 12
                    if iv1 != iv2 or iv1 not in (0, 7):
                        continue
                    kind = "5ths" if iv1 == 7 else "octaves/unisons"
                    both_choir = all(self.inst[self.by_id[q].instrument].section == "choir" for q in (pa, pb))
                    if both_choir:
                        check = "choir_parallels"
                    elif self.links.linked(pa, pb):
                        continue
                    else:
                        check = "parallels"
                    self.add(check,
                             f"Parallel {kind}: {self.pname(pa)} ({self.n(a1)}→{self.n(a2)}) and "
                             f"{self.pname(pb)} ({self.n(b1)}→{self.n(b2)}) into {self.where(s2.start, i + 1)}.",
                             [pa, pb], i + 1, s2.start, [a1, a2, b1, b2])

    def check_doubled_outer(self):
        lt = (self.key.tonic_pc + 11) % 12
        for i, span in enumerate(self.chords):
            sounding = [(p, nt.pitch) for p in self.parts for nt in p.notes if nt.start <= span.start < nt.end]
            if not sounding:
                continue
            chord_pcs = span.label.pcs()
            sensitive = {pc: "7th" for pc in _seventh_pcs(span.label)}
            if lt in chord_pcs:
                sensitive.setdefault(lt, "leading tone")
            if not sensitive:
                continue
            pitches = [pitch for _, pitch in sounding]
            for outer, where_ in ((max(pitches), "top"), (min(pitches), "bass")):
                kind = sensitive.get(outer % 12)
                if kind is None:
                    continue
                outer_parts = [p for p, pitch in sounding if pitch == outer]
                doubling = [(p, pitch) for p, pitch in sounding
                            if pitch % 12 == outer % 12
                            and not any(p.id == q.id or self.links.linked(p.id, q.id) for q in outer_parts)]
                if doubling:
                    ps = sorted({p.id for p in outer_parts} | {p.id for p, _ in doubling})
                    self.add("doubled_outer",
                             f"The {kind} {self.n(outer)} is in the {where_} voice at "
                             f"{self.where(span.start, i)} and is doubled by "
                             f"{', '.join(sorted({self.pname(p.id) for p, _ in doubling}))}.",
                             ps, i, span.start, [outer] + sorted({pitch for _, pitch in doubling}),
                             dedupe=(i, outer))

    def check_melody_clash(self):
        for m in self.parts:
            if m.role != "melody":
                continue
            for mn in m.notes:
                for p in self.parts:
                    if p.id == m.id or p.role == "melody" or self.links.linked(p.id, m.id):
                        continue
                    for nt in p.notes:
                        if nt.start < mn.end and nt.end > mn.start and abs(nt.pitch - mn.pitch) in self.rules.melody_clash:
                            t = max(nt.start, mn.start)
                            c = self.chord_at(t)
                            self.add("melody_clash",
                                     f"Melody {self.pname(m.id)} {self.n(mn.pitch)} clashes with "
                                     f"{self.pname(p.id)} {self.n(nt.pitch)} at {self.where(t, c)} (a minor 2nd).",
                                     [m.id, p.id], c, t, [mn.pitch, nt.pitch],
                                     dedupe=(m.id, p.id, c, mn.pitch, nt.pitch))

    def run(self) -> Report:
        self.check_ranges()
        self.check_defining_tones()
        self.check_vertical(self.slices())
        self.check_choir_leaps()
        self.check_parallels()
        self.check_doubled_outer()
        self.check_melody_clash()
        return Report(self.issues)


def check(parts: list[Part], chords: list[ChordSpan], key: Key, mode: str = SAFE, *,
          rules: Rules | None = None, instruments: dict[str, Instrument] | None = None,
          name_style: str = "ableton") -> Report:
    """Run every SPEC §7 check. `mode` is "safe" or "moderate"."""
    if mode not in (SAFE, "moderate"):
        raise ValueError(f"mode must be safe or moderate, not {mode!r}")
    return _Checker(parts, chords, key, mode, rules or builtin_rules(),
                    instruments or builtin_instruments(), name_style).run()
