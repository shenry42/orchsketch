"""Milestone 4 control: lock and regenerate, regenerate one part / one chord, per-chord swap."""
from pathlib import Path

import pytest

from orchsketch.edits import bar_chords, origin, regenerate, regenerate_chord, regenerate_part, swap, unswap
from orchsketch.generator import APPROACHES, GenerationError, generate_all
from test_generator import EXPECTED, load, must_fix

FILES = [EXPECTED[0], EXPECTED[7], EXPECTED[10]]  # 4 bars, 2 chords per bar, 16 bars


@pytest.fixture(scope="module", params=FILES, ids=lambda p: p.name.split(".")[0])
def alts(request):
    chords, key = load(request.param)
    return generate_all(chords, key, seed=1)


def sounding(o):
    return [ln.id for ln in o.sounding_lines]


def test_regenerate_keeps_locked_parts_and_changes_the_rest(alts):
    for a in APPROACHES:
        o = alts[a]
        ids = sounding(o)
        locked = {ids[0], ids[len(ids) // 2]}
        r = regenerate(o, locked)
        for lid in locked:
            assert r.cells[lid] == o.cells[lid]
        assert any(r.cells[lid] != o.cells[lid] for lid in o.cells if lid not in locked)
        assert not must_fix(r.report, locked), (a, r.report.text())
        assert r.meta["variation"] == 1 and r.approach == a
        assert regenerate(o, locked).cells == r.cells  # deterministic


def test_regenerate_with_a_locked_choir_line_keeps_choir_rules(alts):
    o = alts["A"]
    r = regenerate(o, {"ch-s", "vc"})
    assert r.cells["ch-s"] == o.cells["ch-s"]
    assert not r.report.errors, r.report.text()


def test_regenerate_one_part_changes_only_that_part(alts):
    o = alts["A"]
    for lid in ("hn2", "vla", "ch-a"):
        r = regenerate_part(o, lid)
        assert r.cells[lid] != o.cells[lid]
        assert all(r.cells[x] == o.cells[x] for x in o.cells if x != lid)
        assert [p is None for p in r.cells[lid]] == [p is None for p in o.cells[lid]]  # same rhythm
        assert not must_fix(r.report), (lid, r.report.text())
        assert r.part(lid).doubles is None  # its own line now
        # the chord's bass note is unchanged
        for i, span in enumerate(o.chords):
            low = min(r.cells[x][i] for x in r.cells if r.cells[x][i] is not None)
            assert low % 12 == span.label.bass


def test_regenerate_one_chord_changes_only_that_chord(alts):
    for a in APPROACHES:
        o = alts[a]
        i = len(o.chords) // 2
        r = regenerate_chord(o, i, {"vc"})
        assert r.cells["vc"] == o.cells["vc"]
        assert any(r.cells[x][i] != o.cells[x][i] for x in o.cells)
        for x in o.cells:
            assert r.cells[x][:i] == o.cells[x][:i] and r.cells[x][i + 1:] == o.cells[x][i + 1:]
        assert not must_fix(r.report, {"vc"}), (a, r.report.text())


def test_swap_takes_the_other_voicing_and_flags_bigger_leaps(alts):
    o, b = alts["A"], alts["B"]
    s = swap(o, b, [1], {"vc"})
    assert s.sources[1] == "B" and s.sources[0] == "A"
    for x in o.cells:
        if x != "vc":
            assert s.cells[x][1] == b.cells[x][1]
        assert s.cells[x][0] == o.cells[x][0]
    assert s.cells["vc"] == o.cells["vc"]  # locked parts stay
    leaps = s.report.by_check("swap_leap")
    for issue in leaps:  # only on the chords next to the swap, and only when the leap got bigger
        assert issue.chord in (1, 2) and abs(issue.pitches[1] - issue.pitches[0]) >= 8
    # back to own voicing gives the original back, without flags
    u = unswap(s, [1])
    assert u.cells == o.cells and all(src == "A" for src in u.sources) and not u.report.by_check("swap_leap")
    assert origin(s) is o


def test_swap_a_whole_bar(alts):
    o, c = alts["A"], alts["C"]
    idx = bar_chords(o, len(o.chords) - 1)
    s = swap(o, c, idx)
    assert [s.sources[i] for i in idx] == ["C"] * len(idx)
    assert all(src == "A" for i, src in enumerate(s.sources) if i not in idx)


def test_a_swap_that_breaks_a_rule_is_kept_and_flagged():
    chords, key = load(EXPECTED[0])
    alts = generate_all(chords, key, seed=1)
    s = swap(alts["A"], alts["C"], [3])
    assert s.report.errors  # the choir bass leaps over an octave: shown red, undo is the user's call
    assert all(i.chord in (2, 3) for i in s.report.errors)


def test_nothing_to_regenerate_messages(alts):
    o = alts["A"]
    with pytest.raises(GenerationError):
        regenerate_part(o, "picc")  # rests throughout in A
