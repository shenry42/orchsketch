import pytest

import checker_examples as ex
from helpers import block, write_mid
from orchsketch.analysis import AnalysisSession, parse_symbol
from orchsketch.checker import ChordSpan, Part, check, chords_from_session, required_tones
from orchsketch.midi_io import PPQ, Note, read_chord_file
from orchsketch.theory import Key, parse_pitch


@pytest.mark.parametrize("case", ex.CASES, ids=lambda c: c[0])
def test_hand_made_case(case):
    _, _, build, expected = case
    parts, chords, key = build()
    report = check(parts, chords, key)
    assert {i.check for i in report.issues} == expected, report.text()


@pytest.mark.parametrize("build", [ex.clean_epic_staple, ex.clean_harmonic_minor])
def test_clean_orchestrations(build):
    parts, chords, key = build()
    for mode in ("safe", "moderate"):
        report = check(parts, chords, key, mode)
        assert report.issues == [], report.text()
        assert report.ok and report.summary() == "Checker: no problems."


def test_doublings_hide_their_parallels_but_independent_copies_dont():
    parts, chords, key = ex.clean_epic_staple()
    # Horn 2 no longer marked as doubling Violins I: its octaves with the melody line now count.
    parts = [Part(p.id, p.instrument, p.notes, p.role) if p.id == "hn2" else p for p in parts]
    par = check(parts, chords, key).by_check("parallels")
    assert par and all("hn2" in i.parts for i in par)
    assert {q for i in par for q in i.parts} == {"hn2", "vln1", "s"}


def test_comfortable_range_severity_depends_on_mode():
    parts, chords, key = ex.CASES[2][2]()
    assert check(parts, chords, key, "safe").errors
    moderate = check(parts, chords, key, "moderate")
    assert moderate.ok and len(moderate.warnings) == 2


def test_messages_name_part_note_and_place():
    parts, chords, key = ex.CASES[1][2]()
    issue = check(parts, chords, key).issues[0]
    assert issue.parts == ("tba",) and issue.chord == 0 and issue.tick == 0
    assert issue.message == "Tuba: G3 at bar 1 beat 1 (C) is outside the playable range D0–F3."
    sci = check(parts, chords, key, name_style="scientific").issues[0]
    assert "G4" in sci.message and "D1–F4" in sci.message


def test_low_interval_boundaries():
    key = Key("C", "minor")
    chords = ex.chords(["Cm"])
    ok = [ex.part("vc", "cellos", ["C3"], role="bass"), ex.part("vla", "violas", ["Eb3"]),
          ex.part("vln", "violins_2", ["G3"])]
    assert not check(ok, chords, key).by_check("low_interval")  # C3-Eb3 is exactly at the limit
    low = [ex.part("vc", "cellos", ["C2"], role="bass"), ex.part("bn", "bassoon", ["Eb2"]),
           ex.part("vla", "violas", ["G3"])]
    issues = check(low, chords, key).by_check("low_interval")
    assert len(issues) == 1 and issues[0].pitches == (parse_pitch("C2"), parse_pitch("Eb2"))
    assert "minor 3rd" in issues[0].message


def test_compound_intervals_and_octaves_have_no_limit():
    key = Key("C", "major")
    parts = [ex.part("cb", "basses", ["C1"]), ex.part("vc", "cellos", ["C2"]), ex.part("bn", "bassoon", ["E3"]),
             ex.part("vla", "violas", ["G3"])]
    assert not check(parts, ex.chords(["C"]), key).by_check("low_interval")


def test_unison_doubling_counts_once_for_low_intervals():
    key = Key("C", "major")
    parts = [ex.part("vc", "cellos", ["C3"]), ex.part("bn", "bassoon", ["C3"]), ex.part("vla", "violas", ["E3"]),
             ex.part("vln", "violins_2", ["G3"])]
    assert check(parts, ex.chords(["C"]), key).issues == []


def test_required_tones():
    names = lambda s: sorted(required_tones(parse_symbol(s)).values())
    assert names("C") == ["3rd", "root"]
    assert names("Cdim") == ["3rd", "5th", "root"]
    assert names("C5") == ["5th", "root"]
    assert names("Csus2") == ["2nd", "5th", "root"]
    assert names("Csus4") == ["4th", "5th", "root"]
    assert names("C6") == ["3rd", "5th", "6th", "root"]
    assert names("Cadd9") == ["3rd", "9th", "root"]
    assert names("Cm9") == ["3rd", "7th", "9th", "root"]
    assert names("Cdim7") == ["3rd", "5th", "7th", "root"]
    assert names("Bb/C") == ["3rd", "bass note", "root"]


def test_missing_tone_named_in_key_spelling():
    key = Key("Eb", "major")
    parts = [ex.part("vc", "cellos", ["Eb3"]), ex.part("vla", "violas", ["Bb3"])]
    issue = check(parts, ex.chords(["Eb"]), key).by_check("defining_tone")[0]
    assert issue.message == "Eb at bar 1 beat 1: the 3rd (G) is missing."


def test_nothing_sounding_is_reported():
    key = Key("C", "major")
    parts = [ex.part("vc", "cellos", ["C3", None]), ex.part("vla", "violas", ["E3", None])]
    report = check(parts, ex.chords(["C", "G"]), key)
    assert [i.message for i in report.by_check("defining_tone")] == ["G at bar 2 beat 1: nothing sounds."]


def test_ostinato_rhythm_and_held_notes():
    """Notes shorter than the chord (patterns) and notes held across a change both work."""
    key = Key("A", "minor")
    chords = ex.chords(["Am", "F"])
    eighths = tuple(Note(parse_pitch(p), i * PPQ // 2, (i + 1) * PPQ // 2)
                    for i, p in enumerate(["A2"] * 8 + ["F2"] * 8))
    held = (Note(parse_pitch("C4"), 0, 8 * PPQ),)  # common tone tied through the change
    parts = [Part("vc", "cellos", eighths, role="bass"),
             Part("vla", "violas", (Note(parse_pitch("E3"), 0, 4 * PPQ), Note(parse_pitch("F3"), 4 * PPQ, 8 * PPQ))),
             Part("vln2", "violins_2", held),
             Part("vln1", "violins_1", (Note(parse_pitch("A4"), 0, 8 * PPQ),))]
    assert check(parts, chords, key).issues == []


def test_choir_parallels_are_errors_even_when_marked_as_doubling():
    parts, chords, key = ex.CASES[-1][2]()
    parts = [Part(p.id, p.instrument, p.notes, doubles="b" if p.id == "t" else None) for p in parts]
    report = check(parts, chords, key)
    assert [i.check for i in report.errors] == ["choir_parallels"]


def test_doubled_seventh_in_bass():
    key = Key("C", "major")
    parts = [ex.part("vc", "cellos", ["F2"], role="bass"), ex.part("vla", "violas", ["B3"]),
             ex.part("vln2", "violins_2", ["D4"]), ex.part("vln1", "violins_1", ["F4", ]),
             ex.part("tpt", "trumpet", ["G4"])]
    issues = check(parts, ex.chords(["G7/F"]), key).by_check("doubled_outer")
    assert len(issues) == 1 and "The 7th F1 is in the bass voice" in issues[0].message


def test_chords_from_session(tmp_path):
    clip = read_chord_file(write_mid(tmp_path / "c.mid", block([([57, 60, 64], 4), ([53, 57, 60], 4)])))
    s = AnalysisSession(clip, Key("A", "minor"))
    with pytest.raises(ValueError, match="isn't confirmed"):
        chords_from_session(s)
    s.confirm_all()
    spans = chords_from_session(s)
    assert [(c.start, c.end, c.label.symbol(s.key)) for c in spans] == [(0, 1920, "Am"), (1920, 3840, "F")]


def test_bad_input():
    key = Key("C", "major")
    with pytest.raises(ValueError, match="unknown instrument"):
        check([ex.part("x", "kazoo", ["C4"])], ex.chords(["C"]), key)
    with pytest.raises(ValueError, match="unique"):
        check([ex.part("x", "cellos", ["C3"]), ex.part("x", "violas", ["E3"])], ex.chords(["C"]), key)
    with pytest.raises(ValueError, match="doubles unknown part"):
        check([ex.part("x", "cellos", ["C3"], doubles="y")], ex.chords(["C"]), key)
    with pytest.raises(ValueError, match="mode"):
        check([], [], key, "wild")
    with pytest.raises(ValueError, match="role"):
        ex.part("x", "cellos", ["C3"], role="lead")


def test_report_helpers():
    parts, chords, key = ex.CASES[1][2]()
    r = check(parts, chords, key)
    assert r.for_part("tba") == r.issues and r.for_chord(1) == [r.issues[1]]
    assert r.summary() == "Checker: 2 errors, 0 warnings."
    assert r.text().splitlines()[1].startswith("  [ERROR  ] Tuba: G3")
    assert ChordSpan(0, 1, parse_symbol("C")).label.quality == "maj"
