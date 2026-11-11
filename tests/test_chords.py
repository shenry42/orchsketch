import pytest

from orchsketch.analysis.chords import ChordLabel, label_pitches
from orchsketch.analysis.symbols import SymbolError, parse_symbol
from orchsketch.theory import Key

AM = Key("A", "minor")
C = Key("C", "major")


def best(pitches, key, pedal=False):
    c = label_pitches(pitches, key, pedal)
    assert c and c[0].exact, f"unrecognized: {c}"
    return c[0].label.symbol(key), c[0].label.roman(key), [x.label.symbol(key) for x in c[1:]]


# (pitches, key, expected symbol, expected roman)
CASES = [
    ([45, 57, 60, 64], AM, "Am", "i"),
    ([41, 57, 60, 65], AM, "F", "VI"),
    ([48, 55, 60, 64], C, "C", "I"),
    ([52, 55, 60, 64], AM, "C/E", "III6"),
    ([43, 55, 60, 64], C, "C/G", "I64"),
    ([40, 56, 59, 62, 64], AM, "E7", "V7"),
    ([44, 59, 62, 64], AM, "E7/G#", "V65"),
    ([47, 57, 62, 65], AM, "Bm7b5", "iiø7"),  # B D F A
    ([44, 59, 62, 65], AM, "G#dim7", "vii°7"),
    ([41, 57, 62, 65], AM, "Dm/F", "iv6"),
    ([43, 55, 59, 62, 65], C, "G7", "V7"),
    ([48, 55, 59, 60, 64], C, "Cmaj7", "Imaj7"),
    ([45, 57, 64], AM, "A5", "i5"),
    ([50, 55, 57, 62], Key("D", "major"), "Dsus4", "Isus4"),
    ([43, 55, 57, 62], Key("D", "major"), "Gsus2", "IVsus2"),
    ([48, 56, 60, 63], C, "Ab/C", "bVI6"),
    ([53, 56, 60, 65], C, "Fm", "iv"),
    ([48, 55, 60, 62, 64], C, "Cadd9", "Iadd9"),
    ([43, 57, 59, 62, 65], C, "G9", "V9"),
    ([48, 56, 60, 64], C, "Caug", "I+"),
    ([47, 59, 62, 65], C, "Bdim", "vii°"),
]


@pytest.mark.parametrize("pitches,key,symbol,roman", CASES)
def test_labels(pitches, key, symbol, roman):
    s, r, _ = best(pitches, key)
    assert (s, r) == (symbol, roman)


def test_am7_vs_c6_bass_decides_and_other_is_alternative():
    s, r, alts = best([45, 55, 57, 60, 64], AM)
    assert (s, r) == ("Am7", "i7") and "C6/A" in alts
    s, r, alts = best([48, 57, 60, 64, 67], AM)
    assert (s, r) == ("C6", "IIIadd6") and "Am7/C" in alts


def test_power_chord_offers_triads_as_alternatives():
    s, _, alts = best([45, 57, 64], AM)
    assert s == "A5" and alts[0] == "Am"  # in-key triad first
    s, _, alts = best([45, 57, 64], Key("A", "major"))
    assert s == "A5" and alts[0] == "A"


def test_pedal_upper_structure():
    s, r, _ = best([36, 58, 62, 65], Key("C", "minor"), pedal=True)
    assert (s, r) == ("Bb/C", "VII/C")


def test_unrecognized_chord():
    cands = label_pitches([48, 49, 50, 51], C)  # chromatic cluster
    assert not cands or not cands[0].exact


def test_alternatives_capped():
    assert len(label_pitches([45, 55, 57, 60, 64], AM)) <= 4


@pytest.mark.parametrize("text,root,quality,bass", [
    ("Am7", 9, "m7", 9), ("C/E", 0, "maj", 4), ("Bbmaj7", 10, "maj7", 10), ("F#m7b5", 6, "m7b5", 6),
    ("A5", 9, "5", 9), ("Dsus", 2, "sus4", 2), ("Ebø7", 3, "m7b5", 3), ("C-7", 0, "m7", 0),
    ("GM7", 7, "maj7", 7), ("bbm", 10, "min", 10), ("Ab/C", 8, "maj", 0), (" e7 ", 4, "7", 4),
])
def test_parse_symbol(text, root, quality, bass):
    assert parse_symbol(text) == ChordLabel(root, quality, bass)


@pytest.mark.parametrize("text", ["", "H7", "C13", "Cmaj7#11", "C/X"])
def test_parse_symbol_rejects(text):
    with pytest.raises(SymbolError):
        parse_symbol(text)
