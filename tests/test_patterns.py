"""Milestone 7 (v1.2): patterns as data, the shape-preserving engine, note modes and accent groupings.

The six v1 patterns must render exactly as v1.1 did (a frozen copy of v1.1's patterns.py is the reference)."""
import itertools
import json

import pytest

import legacy_patterns_v11 as old
from orchsketch import patterns as pat
from orchsketch.midi_io import BAR, PPQ
from orchsketch.theory import Key

EIGHTH, SIXTEENTH = PPQ // 2, PPQ // 4


def spans():
    """Chord spans on the 8th grid: every start in a bar, lengths from an 8th to two bars and a bit."""
    for start in range(0, BAR, EIGHTH):
        for length in list(range(EIGHTH, 2 * BAR + 1, EIGHTH)) + [3 * BAR + EIGHTH]:
            yield start + BAR, start + BAR + length


@pytest.mark.parametrize("pt", pat.V1_PATTERNS)
def test_v1_patterns_render_exactly_as_v11(pt):
    n = 0
    for (s, e), vel, alt, passing in itertools.product(spans(), (30, 80, 120), (None, 55), (None, 62)):
        if pt != pat.SIXTEENTHS_ALT and alt is not None:
            continue
        want = old.render(pt, 60, s, e, vel, alt=alt, passing=passing if pt in old.PASSING_PATTERNS else None)
        got = pat.render(pt, 60, s, e, vel, alt=alt, passing=passing if pt in pat.PASSING_PATTERNS else None)
        assert got == want, (pt, s, e, vel, alt, passing)
        n += 1
    assert n > 100


def test_v1_tables_unchanged():
    assert pat.PATTERNS[:6] == old.PATTERNS
    assert {k: pat.PATTERN_NAMES[k] for k in old.PATTERNS} == old.PATTERN_NAMES
    assert {k: pat.PATTERN_SHORT[k] for k in old.PATTERN_SHORT} == old.PATTERN_SHORT
    assert set(old.CHOIR_PATTERNS) <= set(pat.CHOIR_PATTERNS)
    assert set(pat.PASSING_PATTERNS) == set(old.PASSING_PATTERNS)
    for p in pat.PATTERNS:
        assert pat.allowed(p, False)
    for p in old.PATTERNS:
        assert pat.allowed(p, True) == old.allowed(p, True)
    assert pat.passing_pitch(60, 64, Key("C", "major").scale_pcs()) == 62
    assert pat.split_at_bars(old.split_at_bars([])) == []


def test_every_pattern_file_is_valid_and_strikes_its_anchor():
    for pid, p in pat.library().items():
        assert (pat.PATTERN_DIR / f"{pid}.json").exists(), pid
        for s, e in [(0, BAR), (EIGHTH, BAR), (BAR + 3 * EIGHTH, 3 * BAR)]:
            notes = pat.render(pid, 60, s, e, 100, mapper=lambda o, oc, st: 60 + o + 12 * oc)
            assert notes[0].start == s and notes[0].pitch == 60, pid  # every pattern strikes the chord
            assert all(s <= n.start < n.end <= e for n in notes), pid
            assert all(a.end <= b.start for a, b in zip(notes, notes[1:])), pid  # monophonic
            if p.end_on_anchor:
                assert notes[-1].pitch == 60, pid
        assert p.choir == (pid in pat.CHOIR_PATTERNS)
        assert pid in pat.family(pid)


def test_bad_pattern_files_are_rejected():
    good = json.loads((pat.PATTERN_DIR / "8ths_rise.json").read_text(encoding="utf-8"))
    with pytest.raises(pat.PatternError):
        pat._parse_pattern(dict(good, contour=[1, 0]), "x.json")  # must start on the anchor
    with pytest.raises(pat.PatternError):
        pat._parse_pattern(dict(good, choir=True), "x.json")  # choirs repeat their note only
    with pytest.raises(pat.PatternError):
        pat._parse_pattern(dict(good, kind="hits", hits=[0, 8], passing=True), "x.json")
    with pytest.raises(pat.PatternError):
        pat._parse_pattern(dict(good, kind="arp"), "x.json")


def test_groupings_fill_a_bar_and_set_accents_and_length():
    g = pat.groupings()
    assert set(g) >= {"3+3+2", "3+3+3+3+2+2", "4+4+3+3+2"}
    assert g["3+3+2"].starts == (0, 3 * EIGHTH, 6 * EIGHTH)
    assert g["4+4+3+3+2"].starts == (0, 4 * SIXTEENTH, 8 * SIXTEENTH, 11 * SIXTEENTH, 14 * SIXTEENTH)
    notes = pat.render(pat.EIGHTHS, 60, 0, BAR, 100, grouping="3+3+2")
    assert [n.velocity for n in notes] == [100, 80, 80, 100, 80, 80, 100, 80]
    assert all(n.length == EIGHTH for n in notes)
    short = pat.render(pat.SIXTEENTHS, 60, 0, BAR, 100, grouping="3+3+3+3+2+2 short")
    acc = [n for n in short if n.velocity == 100]
    assert [n.start // SIXTEENTH for n in acc] == [0, 3, 6, 9, 12, 14]
    assert all(n.length == SIXTEENTH for n in acc)
    assert all(n.length < SIXTEENTH for n in short if n.velocity != 100)
    # hits patterns keep their own accents
    assert pat.render(pat.STABS, 60, 0, BAR, 100, grouping="3+3+2") == pat.render(pat.STABS, 60, 0, BAR, 100)


C_MAJOR = {0, 4, 7}


def test_note_modes():
    key = Key("C", "major")
    sc = pat.chord_scale(C_MAJOR, key)
    assert sc == {0, 2, 4, 5, 7, 9, 11}
    ok = lambda q: 48 <= q <= 84  # noqa: E731
    chord = pat.make_mapper(60, C_MAJOR, sc, pat.CHORD_TONES, ok)
    scale = pat.make_mapper(60, C_MAJOR, sc, pat.SCALE_STEPS, ok)
    hybrid = pat.make_mapper(60, C_MAJOR, sc, pat.HYBRID, ok)
    assert [chord(k, 0, False) for k in (1, 2, 3, -1, -2)] == [64, 67, 72, 55, 52]
    assert [scale(k, 0, False) for k in (1, 2, 3, -1, -2)] == [62, 64, 65, 59, 57]
    assert hybrid(1, 0, False) == 62 and hybrid(1, 0, True) == 64  # strong notes snap to a chord tone
    assert hybrid(3, 0, True) == 64  # F snaps down to E (nearest)
    # E major in A minor: G# replaces G in the chord's scale
    assert pat.chord_scale({4, 8, 11}, Key("A", "minor")) == {9, 11, 0, 2, 4, 5, 8}
    assert pat.chord_scale({5, 8, 0}, key) == {0, 2, 4, 5, 7, 8, 11}  # Fm in C major: Ab for A
    # range: mirrored, then the anchor
    high = pat.make_mapper(79, C_MAJOR, sc, pat.CHORD_TONES, lambda q: 48 <= q <= 82)
    assert high(1, 0, False) == 76  # C6 above is out: the step below
    assert pat.make_mapper(60, C_MAJOR, sc, pat.CHORD_TONES, lambda q: q == 60)(2, 0, False) == 60
    octv = pat.make_mapper(80, C_MAJOR | {8}, sc, pat.CHORD_TONES, ok)
    assert octv(0, 1, False) == 68  # an octave up is out of range: an octave down


def test_shape_pattern_keeps_its_shape_on_a_new_chord():
    key = Key("C", "major")
    ok = lambda q: 40 <= q <= 90  # noqa: E731
    for anchor, pcs in ((60, C_MAJOR), (62, {2, 5, 9}), (64, {4, 7, 11, 2})):
        m = pat.make_mapper(anchor, pcs, pat.chord_scale(pcs, key), pat.CHORD_TONES, ok)
        notes = pat.render("8ths_rise", anchor, 0, BAR, 100, mapper=m)
        ps = [n.pitch for n in notes]
        assert ps[0] == anchor and ps[1] > ps[0] and ps[2] > ps[1] and ps[3] < ps[2]  # 1-2-3-2
        assert all(p % 12 in pcs for p in ps)
