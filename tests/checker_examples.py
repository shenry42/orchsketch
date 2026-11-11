"""Hand-made textures for the rule checker (Milestone 2).

Pitches are scientific names (C4 = middle C), one entry per chord: a name, a list of names
(several notes at once) or None (rest). Used by tests/test_checker.py and scripts/checker_report.py.
"""
from orchsketch.analysis import parse_symbol
from orchsketch.checker import ChordSpan, Part
from orchsketch.midi_io import PPQ, Note
from orchsketch.theory import Key, parse_pitch


def part(pid, instrument, pitches, beats=4, **kw) -> Part:
    notes, t = [], 0
    for entry in pitches:
        length = int(beats * PPQ)
        if entry is not None:
            for name in [entry] if isinstance(entry, str) else entry:
                notes.append(Note(parse_pitch(name), t, t + length, 100))
        t += length
    return Part(pid, instrument, tuple(notes), **kw)


def chords(symbols, beats=4) -> list[ChordSpan]:
    out, t = [], 0
    for s in symbols:
        length = int(beats * PPQ)
        out.append(ChordSpan(t, t + length, parse_symbol(s)))
        t += length
    return out


def clean_epic_staple():
    """Test 1 (A minor, Am F C G): four voices in the strings, everything else doubles them.

    Basses/tuba-style octave doubling under the cellos, horns and choir on the inner voices.
    """
    key = Key("A", "minor")
    parts = [
        part("hn1", "horn", ["E4", "F4", "E4", "D4"], doubles="vla"),
        part("hn2", "horn", ["A3", "A3", "G3", "G3"], doubles="vln1"),
        part("vln1", "violins_1", ["A4", "A4", "G4", "G4"], role="melody"),
        part("vln2", "violins_2", ["C4", "C4", "C4", "B3"], role="high_harmony"),
        part("vla", "violas", ["E3", "F3", "E3", "D3"], role="mid_harmony"),
        part("vc", "cellos", ["A2", "F2", "C3", "G2"], role="bass"),
        part("cb", "basses", ["A1", "F1", "C2", "G1"], role="bass", doubles="vc"),
        part("s", "choir_soprano", ["A4", "A4", "G4", "G4"], role="melody", doubles="vln1"),
        part("a", "choir_alto", ["E4", "F4", "E4", "D4"], doubles="vla"),
        part("t", "choir_tenor", ["C4", "C4", "C4", "B3"], doubles="vln2"),
        part("b", "choir_bass", ["A3", "F3", "C4", "G3"], doubles="vc"),
    ]
    return parts, chords(["Am", "F", "C", "G"]), key


def clean_harmonic_minor():
    """Test 4 (E minor, Em C Am B): the leading tone D# is in the top voice of B, doubled only
    by its own octave/unison doublings (trumpet), which is allowed."""
    key = Key("E", "minor")
    parts = [
        part("tpt", "trumpet", ["E4", "E4", "E4", "D#4"], doubles="vln1"),
        part("hn1", "horn", ["G3", "G3", "A3", "F#3"], doubles="vla"),
        part("hn2", "horn", ["B3", "C4", "C4", "B3"], doubles="vln2"),
        part("tba", "tuba", ["E2", "C3", "A2", "B2"], role="bass", doubles="vc"),
        part("vln1", "violins_1", ["E4", "E4", "E4", "D#4"], role="melody"),
        part("vln2", "violins_2", ["B3", "C4", "C4", "B3"]),
        part("vla", "violas", ["G3", "G3", "A3", "F#3"]),
        part("vc", "cellos", ["E2", "C3", "A2", "B2"], role="bass"),
        part("cb", "basses", ["E1", "C2", "A1", "B1"], role="bass", doubles="vc"),
    ]
    return parts, chords(["Em", "C", "Am", "B"]), key


def _base(**changes):
    """C major, C -> G: a clean four-part string texture that each case changes in one place."""
    lines = {
        "vln1": ("violins_1", ["C5", "B4"], {"role": "melody"}),
        "vln2": ("violins_2", ["E4", "D4"], {}),
        "vla": ("violas", ["G3", "G3"], {}),
        "vc": ("cellos", ["C3", "G2"], {"role": "bass"}),
    }
    extra = changes.pop("extra", [])
    symbols = changes.pop("symbols", ["C", "G"])
    for pid, pitches in changes.items():
        inst, _, kw = lines[pid]
        lines[pid] = (inst, pitches, kw)
    parts = [part(pid, inst, p, **kw) for pid, (inst, p, kw) in lines.items()] + extra
    return parts, chords(symbols), Key("C", "major")


def _choir(s, a, t, b):
    return [part("s", "choir_soprano", s), part("a", "choir_alto", a),
            part("t", "choir_tenor", t), part("b", "choir_bass", b)]


def _choir_only(s, a, t, b):
    return _choir(s, a, t, b), chords(["C", "G"]), Key("C", "major")


# (id, what it shows, builder, checks it must trigger -- and nothing else)
CASES = [
    ("clean_base", "Clean four-part strings, C -> G", lambda: _base(), set()),
    ("playable_range", "Tuba on G4, above its playable top F4",
     lambda: _base(extra=[part("tba", "tuba", ["G4", "G4"])]), {"playable_range"}),
    ("comfortable_range", "Tuba on D4: playable, but above its comfortable top C4",
     lambda: _base(extra=[part("tba", "tuba", ["D4", "D4"])]), {"comfortable_range"}),
    ("defining_tone", "Chord labelled C7 but no Bb anywhere",
     lambda: _base(symbols=["C7", "G"]), {"defining_tone"}),
    ("low_interval", "Bassoon E2 under cello C3: a minor 6th below its F2 limit",
     lambda: _base(extra=[part("bn", "bassoon", ["E2", None])]), {"low_interval"}),
    ("spacing", "Violins I jump to C6: 20 semitones above Violins II",
     lambda: _base(vln1=["C6", "B5"]), {"spacing"}),
    ("parallels", "Violas G3->D3 with cellos C3->G2: parallel 5ths between independent lines",
     lambda: _base(vla=["G3", "D3"]), {"parallels"}),
    ("parallels_linked", "Same 5ths, but violas and cellos share a power-chord group: allowed",
     lambda: _linked_power(), set()),
    ("doubled_outer", "Leading tone B in the top voice (B4) doubled by Violins II (B3)",
     lambda: _base(vln2=["E4", "B3"]), {"doubled_outer"}),
    ("melody_clash", "Oboe B4 against the melody's C5: a minor 2nd",
     lambda: _base(extra=[part("ob", "oboe", ["B4", None])]), {"melody_clash"}),
    ("choir_clean", "Clean SATB choir, C -> G",
     lambda: _choir_only(["C5", "B4"], ["E4", "D4"], ["G3", "G3"], ["C3", "G2"]), set()),
    ("choir_crossing", "Tenor E4 above alto C4",
     lambda: _choir_only(["C5", "B4"], ["C4", "G4"], ["E4", "D4"], ["C3", "G2"]), {"choir_crossing"}),
    ("choir_leap", "Soprano leaps E4 -> G5 (15 semitones)",
     lambda: _choir_only(["E4", "G5"], ["C4", "G4"], ["G3", "B3"], ["C3", "G2"]), {"choir_leap"}),
    ("choir_parallels", "Tenor G3->D3 with bass C3->G2: parallel 5ths inside the choir",
     lambda: _choir_only(["C5", "B4"], ["E4", "D4"], ["G3", "D3"], ["C3", "G2"]), {"choir_parallels"}),
]


def _linked_power():
    parts, chs, key = _base(vla=["G3", "D3"])
    parts = [Part(p.id, p.instrument, p.notes, p.role, p.doubles, "power" if p.id in ("vla", "vc") else None)
             for p in parts]
    return parts, chs, key
