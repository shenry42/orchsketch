"""Basic pitch, key and note-name helpers shared by every module.

Pitch numbers are MIDI numbers. Scientific pitch: C4 = 60 (middle C).
Ableton names middle C "C3", i.e. one octave lower in the label.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

LETTERS = "CDEFGAB"
LETTER_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
ACCIDENTAL_SHIFT = {"": 0, "#": 1, "b": -1, "##": 2, "bb": -2}

MAJOR_STEPS = (0, 2, 4, 5, 7, 9, 11)
NATURAL_MINOR_STEPS = (0, 2, 3, 5, 7, 8, 10)

# Tonic choices offered in the UI (the usual spellings).
MAJOR_TONICS = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
MINOR_TONICS = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B")

# Neutral spelling for chromatic notes in keys without sharps/flats (C major / A minor).
_NEUTRAL = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
_SHARPS = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLATS = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")


def parse_note_name(name: str) -> int:
    """'Eb' -> 3. Raises ValueError for anything else."""
    name = name.strip()
    if not name or name[0].upper() not in LETTER_PC:
        raise ValueError(f"not a note name: {name!r}")
    acc = name[1:].replace("♯", "#").replace("♭", "b")
    if acc not in ACCIDENTAL_SHIFT:
        raise ValueError(f"not a note name: {name!r}")
    return (LETTER_PC[name[0].upper()] + ACCIDENTAL_SHIFT[acc]) % 12


def parse_pitch(name: str, style: str = "scientific") -> int:
    """'Bb1' -> 34 (scientific, C4 = 60). With style='ableton', 'C3' -> 60.

    The octave belongs to the letter, so 'B#3' is 60 and 'Cb4' is 59.
    """
    s = name.strip().replace("♯", "#").replace("♭", "b")
    i = 1
    while i < len(s) and s[i] in "#b":
        i += 1
    letter, acc, octave_txt = s[:1], s[1:i], s[i:]
    if letter.upper() not in LETTER_PC or acc not in ACCIDENTAL_SHIFT:
        raise ValueError(f"not a pitch name: {name!r}")
    try:
        octave = int(octave_txt)
    except ValueError:
        raise ValueError(f"not a pitch name: {name!r}") from None
    if style == "ableton":
        octave += 1
    elif style != "scientific":
        raise ValueError(style)
    pitch = (octave + 1) * 12 + LETTER_PC[letter.upper()] + ACCIDENTAL_SHIFT[acc]
    if not 0 <= pitch <= 127:
        raise ValueError(f"pitch out of MIDI range: {name!r}")
    return pitch


def _spell(letter: str, pc: int) -> str:
    diff = (pc - LETTER_PC[letter]) % 12
    if diff > 6:
        diff -= 12
    acc = {0: "", 1: "#", -1: "b", 2: "##", -2: "bb"}.get(diff)
    if acc is None:
        raise ValueError("cannot spell")
    return letter + acc


@dataclass(frozen=True)
class Key:
    tonic: str = "C"  # spelled tonic, e.g. "Eb"
    mode: str = "major"  # "major" or "minor" (minor covers natural + harmonic)

    def __post_init__(self):
        if self.mode not in ("major", "minor"):
            raise ValueError(f"mode must be major or minor, not {self.mode!r}")
        parse_note_name(self.tonic)

    @property
    def tonic_pc(self) -> int:
        return parse_note_name(self.tonic)

    @property
    def steps(self) -> tuple[int, ...]:
        return MAJOR_STEPS if self.mode == "major" else NATURAL_MINOR_STEPS

    def scale_pcs(self) -> set[int]:
        """Diatonic pitch classes. Minor includes the raised 7th (harmonic minor)."""
        pcs = {(self.tonic_pc + s) % 12 for s in self.steps}
        if self.mode == "minor":
            pcs.add((self.tonic_pc + 11) % 12)
        return pcs

    def spelled_scale(self) -> list[str]:
        start = LETTERS.index(self.tonic[0].upper())
        return [
            _spell(LETTERS[(start + i) % 7], (self.tonic_pc + s) % 12)
            for i, s in enumerate(self.steps)
        ]

    def name_table(self) -> list[str]:
        """Name for each pitch class 0..11 in this key."""
        return list(_name_table(self))

    def _build_name_table(self) -> tuple[str, ...]:
        scale = self.spelled_scale()
        if any("b" in n for n in scale):
            table = list(_FLATS)
        elif any("#" in n for n in scale):
            table = list(_SHARPS)
        else:
            table = list(_NEUTRAL)
        for n in scale:
            table[parse_note_name(n)] = n
        if self.mode == "minor":  # leading tone, spelled as the raised 7th degree
            lt_letter = scale[6][0]
            table[(self.tonic_pc + 11) % 12] = _spell(lt_letter, (self.tonic_pc + 11) % 12)
        return tuple(table)

    def pc_name(self, pc: int) -> str:
        return _name_table(self)[pc % 12]

    def label(self) -> str:
        return f"{self.tonic} {self.mode}"


@lru_cache(maxsize=64)
def _name_table(key: Key) -> tuple[str, ...]:
    return key._build_name_table()


def note_name(pitch: int, style: str = "ableton", key: Key | None = None) -> str:
    """MIDI pitch -> 'C3' (Ableton) or 'C4' (scientific) for pitch 60."""
    name = key.pc_name(pitch % 12) if key else _NEUTRAL[pitch % 12]
    octave = pitch // 12 - 1
    if style == "ableton":
        octave -= 1
    elif style != "scientific":
        raise ValueError(style)
    # Spelling can cross an octave boundary (B#, Cb): keep the octave of the letter.
    if name.startswith("Cb"):
        octave += 1
    elif name.startswith("B#"):
        octave -= 1
    return f"{name}{octave}"
