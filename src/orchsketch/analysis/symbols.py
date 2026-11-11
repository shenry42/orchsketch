"""Parse a chord symbol typed by the user, e.g. 'Am7', 'C/E', 'Bbmaj7', 'F#m7b5', 'A5'."""
from __future__ import annotations

import re

from ..theory import parse_note_name
from .chords import ChordLabel

# Accepted spellings -> quality. Matched case-sensitively after the root (M7 vs m7 matters).
_ALIASES = {
    "": "maj", "maj": "maj", "M": "maj",
    "m": "min", "min": "min", "-": "min",
    "dim": "dim", "o": "dim", "°": "dim",
    "aug": "aug", "+": "aug",
    "sus2": "sus2", "sus4": "sus4", "sus": "sus4",
    "5": "5",
    "6": "6", "add6": "6",
    "m6": "m6", "min6": "m6", "-6": "m6",
    "7": "7", "dom7": "7",
    "maj7": "maj7", "M7": "maj7", "Δ": "maj7", "Δ7": "maj7", "ma7": "maj7",
    "m7": "m7", "min7": "m7", "-7": "m7",
    "m7b5": "m7b5", "ø": "m7b5", "ø7": "m7b5", "m7(b5)": "m7b5", "min7b5": "m7b5", "-7b5": "m7b5",
    "dim7": "dim7", "o7": "dim7", "°7": "dim7",
    "add9": "add9", "add2": "add9",
    "9": "9",
    "m9": "m9", "min9": "m9", "-9": "m9",
}

_RE = re.compile(r"^\s*([A-Ga-g](?:##|bb|#|b|♯|♭)?)(.*?)(?:/\s*([A-Ga-g](?:#|b|♯|♭)?))?\s*$")


class SymbolError(ValueError):
    pass


def parse_symbol(text: str) -> ChordLabel:
    m = _RE.match(text or "")
    if not m:
        raise SymbolError(f"'{text}' isn't a chord symbol. Examples: Am7, C/E, Bbmaj7, F#m7b5, A5.")
    root_txt, suffix, bass_txt = m.group(1), m.group(2).strip(), m.group(3)
    root_txt = root_txt[0].upper() + root_txt[1:]
    if suffix not in _ALIASES:
        raise SymbolError(
            f"'{suffix}' isn't in the v1 chord list (maj, m, dim, aug, sus2, sus4, 5, 6, m6, "
            "7, maj7, m7, m7b5, dim7, add9, 9, m9)."
        )
    root = parse_note_name(root_txt)
    bass = parse_note_name(bass_txt[0].upper() + bass_txt[1:]) if bass_txt else root
    return ChordLabel(root, _ALIASES[suffix], bass)
