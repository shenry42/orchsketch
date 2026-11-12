"""Chord vocabulary, template-matching labeller, chord symbols and Roman numerals."""
from __future__ import annotations

from dataclasses import dataclass

from ..theory import LETTERS, Key, _spell, parse_note_name

# quality -> (intervals from root, 5th may be omitted, simplicity prior)
QUALITIES: dict[str, tuple[tuple[int, ...], bool, float]] = {
    "maj": ((0, 4, 7), True, 0.6),
    "min": ((0, 3, 7), True, 0.6),
    "dim": ((0, 3, 6), False, 0.3),
    "aug": ((0, 4, 8), False, 0.2),
    "sus2": ((0, 2, 7), False, 0.3),
    "sus4": ((0, 5, 7), False, 0.3),
    "5": ((0, 7), False, 0.4),
    "6": ((0, 4, 7, 9), False, -0.2),
    "m6": ((0, 3, 7, 9), False, -0.2),
    "7": ((0, 4, 7, 10), True, 0.1),
    "maj7": ((0, 4, 7, 11), True, 0.0),
    "m7": ((0, 3, 7, 10), True, 0.0),
    "m7b5": ((0, 3, 6, 10), False, 0.0),
    "dim7": ((0, 3, 6, 9), False, 0.0),
    "add9": ((0, 2, 4, 7), True, -0.2),
    "9": ((0, 2, 4, 7, 10), True, -0.3),
    "m9": ((0, 2, 3, 7, 10), True, -0.3),
}

SYMBOL_SUFFIX = {
    "maj": "", "min": "m", "dim": "dim", "aug": "aug", "sus2": "sus2", "sus4": "sus4",
    "5": "5", "6": "6", "m6": "m6", "7": "7", "maj7": "maj7", "m7": "m7", "m7b5": "m7b5",
    "dim7": "dim7", "add9": "add9", "9": "9", "m9": "m9",
}

MINOR_FAMILY = {"min", "m6", "m7", "m9", "dim", "m7b5", "dim7"}
NO_THIRD = {"5", "sus2", "sus4"}
SEVENTH_FAMILY = {"7", "maj7", "m7", "m7b5", "dim7", "9", "m9"}
PLAIN_TRIADS = {"maj", "min", "dim", "aug"}

# Third / fifth / seventh of each quality, for bass-role scoring and inversion figures.
_THIRD = {3, 4}
_FIFTH = {6, 7, 8}
_SEVENTH = {10, 11}

# Scoring weights (see SPEC §3: template matching weighted by bass, key and duration).
W_MISSING = 3.0
W_EXTRA = 4.0
W_OMITTED_FIFTH = 0.4
W_KEY_ALL_DIATONIC = 0.6
W_KEY_PER_CHROMATIC = 0.4
PEDAL_BONUS = 2.5
MAX_ALTERNATIVES = 3
ALTERNATIVE_WINDOW = 6.0  # alternatives must score within this of the best


@dataclass(frozen=True)
class ChordLabel:
    root: int  # pitch class 0-11
    quality: str  # key of QUALITIES
    bass: int  # pitch class of the lowest note

    def __post_init__(self):
        if self.quality not in QUALITIES:
            raise ValueError(f"unknown chord quality {self.quality!r}")

    def pcs(self) -> set[int]:
        return {(self.root + i) % 12 for i in QUALITIES[self.quality][0]}

    @property
    def is_slash(self) -> bool:
        return self.bass != self.root

    @property
    def bass_in_chord(self) -> bool:
        return self.bass in self.pcs()

    def symbol(self, key: Key) -> str:
        chromatic = _chromatic_root(self, key)
        root_name = chromatic[1] if chromatic else key.pc_name(self.root)
        s = root_name + SYMBOL_SUFFIX[self.quality]
        if self.is_slash:
            s += "/" + _bass_name(self, key, root_name if chromatic else None)
        return s

    def roman(self, key: Key) -> str:
        return roman_numeral(self, key)


@dataclass(frozen=True)
class Candidate:
    label: ChordLabel
    score: float
    exact: bool  # every pitch class accounted for, nothing required missing
    over_bass: bool = False  # upper structure labelled over a non-chord bass


def _bass_role_score(quality: str, interval: int) -> float:
    ivs = QUALITIES[quality][0]
    if interval == 0:
        return 2.0
    if interval not in ivs:
        return -1.5
    if quality == "dim7":
        return {3: 0.7, 6: 0.4, 9: 0.3}[interval]
    if interval in _THIRD and quality not in NO_THIRD:
        return 0.7
    if interval in _FIFTH:
        return 0.4
    if interval in _SEVENTH:
        return 0.3
    if interval == 9:  # added 6th
        return 0.0
    if interval == 5:  # 4th of a sus4
        return -0.5
    return -1.0  # 9th / 2nd in the bass


def _score(root: int, quality: str, present: set[int], bass: int, key: Key,
           over_bass: bool, pedal: bool) -> Candidate | None:
    ivs, omit5, prior = QUALITIES[quality]
    chord = {(root + i) % 12 for i in ivs}
    fifth = (root + 7) % 12 if 7 in ivs else None
    required = chord - ({fifth} if (omit5 and fifth is not None) else set())
    missing = required - present
    extra = present - chord
    if root not in present or len(missing) + len(extra) > 2:
        return None
    omitted_fifth = fifth is not None and fifth not in present and fifth not in missing
    score = 10.0 - W_MISSING * len(missing) - W_EXTRA * len(extra) + prior
    if omitted_fifth:
        score -= W_OMITTED_FIFTH
    if over_bass:
        score += _bass_role_score(quality, (bass - root) % 12)  # -1.5: not a chord tone
        if pedal:
            score += PEDAL_BONUS
    else:
        score += _bass_role_score(quality, (bass - root) % 12)
    scale = key.scale_pcs()
    chromatic = len(chord - scale)
    score += W_KEY_ALL_DIATONIC if chromatic == 0 else -W_KEY_PER_CHROMATIC * chromatic
    return Candidate(ChordLabel(root, quality, bass), round(score, 3),
                     exact=not missing and not extra, over_bass=over_bass)


def label_pitches(pitches: list[int] | tuple[int, ...], key: Key, pedal: bool = False) -> list[Candidate]:
    """Rank chord labels for the sounding MIDI pitches. Best first, up to 1 + 3 alternatives."""
    if not pitches:
        return []
    bass_pitch = min(pitches)
    bass = bass_pitch % 12
    present = {p % 12 for p in pitches}
    cands: dict[ChordLabel, Candidate] = {}

    def consider(c: Candidate | None):
        if c and (c.label not in cands or cands[c.label].score < c.score):
            cands[c.label] = c

    for root in range(12):
        for q in QUALITIES:
            consider(_score(root, q, present, bass, key, over_bass=False, pedal=pedal))
    # Upper structure over a bass that isn't one of its chord tones (pedal, slash over non-chord bass).
    # Drop only the bass note and octave doublings stacked directly on it (C1+C2 pedal);
    # the same pitch class higher up in the chord is part of the upper structure.
    ordered = sorted(pitches)
    while ordered and ordered[0] % 12 == bass:
        ordered.pop(0)
    upper = {p % 12 for p in ordered}
    if len(upper) >= 2:
        for root in range(12):
            for q in QUALITIES:
                if q in NO_THIRD and (bass - root) % 12 in _THIRD:
                    continue  # the bass is this chord's 3rd: it's a triad, not "5 over a pedal"
                c = _score(root, q, upper, bass, key, over_bass=True, pedal=pedal)
                if c and bass not in c.label.pcs():
                    consider(c)
    ranked = sorted(cands.values(), key=lambda c: (-c.score, not c.exact, len(QUALITIES[c.label.quality][0])))
    if not ranked:
        return []
    best = ranked[0].score
    return [c for c in ranked if c.score >= best - ALTERNATIVE_WINDOW][: 1 + MAX_ALTERNATIVES]


# ---------------------------------------------------------------- Roman numerals
_DEGREES_MAJOR = {0: "I", 1: "bII", 2: "II", 3: "bIII", 4: "III", 5: "IV", 6: "#IV",
                  7: "V", 8: "bVI", 9: "VI", 10: "bVII", 11: "VII"}
_DEGREES_MINOR = {0: "I", 1: "bII", 2: "II", 3: "III", 4: "#III", 5: "IV", 6: "#IV",
                  7: "V", 8: "VI", 9: "#VI", 10: "VII", 11: "#VII"}
_QUALITY_MARK = {"dim": "°", "aug": "+", "m7b5": "ø7", "dim7": "°7"}
_ROMAN_SUFFIX = {"sus2": "sus2", "sus4": "sus4", "5": "5", "6": "add6", "m6": "add6",
                 "add9": "add9", "7": "7", "maj7": "maj7", "m7": "7", "9": "9", "m9": "9"}


def _diatonic_triad_is_minor(interval: int, key: Key) -> bool | None:
    steps = list(key.steps)
    if interval not in steps:
        return None
    i = steps.index(interval)
    third = (steps[(i + 2) % 7] - interval) % 12
    return third == 3


# Generic interval (letter steps above the root) of each chord tone, for spelling chord tones.
_GENERIC = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 4, 7: 4, 8: 4, 9: 5, 10: 6, 11: 6}
_NUMERAL_DEGREE = {"I": 0, "II": 1, "III": 2, "IV": 3, "V": 4, "VI": 5, "VII": 6}


def _tone_name(root_name: str, quality: str, interval: int) -> str:
    generic = 6 if quality == "dim7" and interval == 9 else _GENERIC[interval]
    letter = LETTERS[(LETTERS.index(root_name[0]) + generic) % 7]
    return _spell(letter, (parse_note_name(root_name) + interval) % 12)


def _chromatic_root(label: "ChordLabel", key: Key) -> tuple[str, str] | None:
    """(numeral, root name) for a chord on the tritone above the tonic; None for every other root.

    The tritone root can read as #IV or bV, and its symbol is spelled to match. The spelling that
    gives the chord's own tones the fewest accidentals wins (Bb · bV in E minor, not A# with C## and
    E#; D · bV in G# minor; B · #IV in F minor); on a tie the key's usual spelling decides. Other
    roots keep the key's spelling and the numeral tables.
    """
    if (label.root - key.tonic_pc) % 12 != 6:
        return None
    tonic_letter = LETTERS.index(key.tonic[0].upper())
    best = None
    for numeral, degree in (("#IV", 3), ("bV", 4)):
        letter = LETTERS[(tonic_letter + degree) % 7]
        try:
            name = _spell(letter, label.root)
            cost = sum(len(_tone_name(name, label.quality, i)) - 1 for i in QUALITIES[label.quality][0])
        except ValueError:
            continue
        rank = (cost, name != key.pc_name(label.root))
        if best is None or rank < best[0]:
            best = (rank, numeral, name)
    return (best[1], best[2]) if best else None


def _bass_name(label: "ChordLabel", key: Key, root_name: str | None) -> str:
    """A chord tone in the bass is spelled as in the chord when the root is chromatic."""
    interval = (label.bass - label.root) % 12
    if root_name and interval in QUALITIES[label.quality][0]:
        try:
            return _tone_name(root_name, label.quality, interval)
        except ValueError:
            pass
    return key.pc_name(label.bass)


def roman_numeral(label: ChordLabel, key: Key) -> str:
    interval = (label.root - key.tonic_pc) % 12
    q = label.quality
    chromatic = _chromatic_root(label, key)
    if chromatic:
        numeral = chromatic[0]
    elif key.mode == "minor" and interval == 11 and q in ("dim", "dim7", "m7b5"):
        numeral = "VII"  # leading-tone chord: vii° / vii°7 / viiø7
    else:
        numeral = (_DEGREES_MAJOR if key.mode == "major" else _DEGREES_MINOR)[interval]
    if q in MINOR_FAMILY:
        lower = True
    elif q in NO_THIRD:
        lower = bool(_diatonic_triad_is_minor(interval, key))
    else:
        lower = False
    if lower:  # keep accidentals as written, lowercase the numeral letters
        numeral = "".join(ch.lower() if ch in "IV" else ch for ch in numeral)

    b = (label.bass - label.root) % 12
    ivs = QUALITIES[q][0]
    slash = "/" + _bass_name(label, key, chromatic[1] if chromatic else None)
    mark = _QUALITY_MARK.get(q, "")
    if q in SEVENTH_FAMILY:
        if q in ("m7b5", "dim7"):
            root_form, inv_prefix = numeral + mark, numeral + mark[0]  # iiø7 / iiø65
        else:
            root_form = numeral + _ROMAN_SUFFIX[q]  # V7, Imaj7, ii7, V9
            inv_prefix = numeral + ("maj" if q == "maj7" else "")
        if b == 0:
            return root_form
        if q in ("9", "m9") or b not in ivs:
            return root_form + slash
        figure = "65" if b in _THIRD else "43" if b in _FIFTH else "42"
        return inv_prefix + figure
    if q in PLAIN_TRIADS:
        base = numeral + mark
        if b == 0:
            return base
        if b not in ivs:
            return base + slash
        return base + ("6" if b in _THIRD else "64")
    base = numeral + _ROMAN_SUFFIX[q]
    return base if b == 0 else base + slash
