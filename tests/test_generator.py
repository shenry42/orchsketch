"""Milestone 3 generator: every test progression orchestrates with no checker errors and no
generator_must_pass warnings, in every section combination, deterministically per seed."""
import json
from itertools import combinations
from pathlib import Path

import pytest

import checker_examples as ex
from orchsketch.analysis import AnalysisSession
from orchsketch.checker import check, chords_from_session
from orchsketch.generator import CC1, VELOCITY, Ensemble, GenerationError, generate
from orchsketch.instruments import SECTIONS, instruments
from orchsketch.midi_io import read_chord_file
from orchsketch.rules import rules
from orchsketch.theory import Key

DATA = Path(__file__).parent / "data"
EXPECTED = sorted(DATA.glob("*.expected.json"))
COMBOS = [frozenset(c) for n in range(1, 5) for c in combinations(SECTIONS, n)]


def load(exp_path):
    exp = json.loads(exp_path.read_text(encoding="utf-8"))
    key = Key(exp["key"]["tonic"], exp["key"]["mode"])
    s = AnalysisSession(read_chord_file(DATA / exp["file"]), key)
    assert s.confirm_all() == 0
    return chords_from_session(s), key


def must_fix(report):
    r = rules()
    return [i for i in report.issues if i.severity == "error" or r.checks[i.check].generator_must_pass]


@pytest.fixture(scope="module", params=EXPECTED, ids=lambda p: p.name.split(".")[0])
def progression(request):
    return load(request.param)


def test_full_epic_is_clean(progression):
    chords, key = progression
    for seed in (1, 2, 3):
        o = generate(chords, key, seed=seed)
        assert not must_fix(o.report), o.report.text()
        # re-check independently, as the app does
        assert not must_fix(check(o.parts, chords, key, "safe")), o.report.text()


def test_every_section_combination_is_clean(progression):
    chords, key = progression
    for combo in COMBOS:
        o = generate(chords, key, seed=7, ensemble=Ensemble(combo))
        assert not must_fix(o.report), (sorted(combo), o.report.text())
        assert {instruments()[ln.instrument].section for ln in o.lines} == set(combo)


def test_safe_mode_stays_in_comfortable_range_and_uses_chord_tones(progression):
    chords, key = progression
    o = generate(chords, key, seed=1)
    insts = instruments()
    for p in o.parts:
        for n in p.notes:
            assert insts[p.instrument].is_comfortable(n.pitch), (p.id, n)
            span = next(c for c in chords if c.start <= n.start < c.end)
            allowed = span.label.pcs() | {span.label.bass}
            assert n.pitch % 12 in allowed, (p.id, n, span.label)
            assert n.velocity == VELOCITY


def test_same_seed_same_result_and_seeds_vary():
    chords, key = load(EXPECTED[10])  # 16 bars
    a = generate(chords, key, seed=5)
    b = generate(chords, key, seed=5)
    assert a.cells == b.cells and [p.notes for p in a.parts] == [p.notes for p in b.parts]
    results = {tuple(map(tuple, generate(chords, key, seed=s).cells.values())) for s in range(1, 7)}
    assert len(results) > 1


def test_notes_sustain_for_the_chord_and_tie_over_repeated_chords():
    _, chords, key = ex.clean_epic_staple()[0], ex.chords(["Am", "Am", "F", "F"]), Key("A", "minor")
    o = generate(chords, key, seed=1)
    vc = o.part("vc")
    # cellos: A held through both Am bars as one note, then F held through both F bars
    assert [(n.start, n.end) for n in vc.notes] == [(0, 3840), (3840, 7680)]
    for p in o.parts:  # every note starts on a chord change and lasts to a chord end
        for n in p.notes:
            assert n.start in {c.start for c in chords} and n.end in {c.end for c in chords}


def test_parts_mark_doublings_and_divisi_lines_are_separate():
    chords, key = load(EXPECTED[0])
    o = generate(chords, key, seed=1)
    ids = [p.id for p in o.parts]
    assert "vln1-a" in ids and "vln1-b" in ids
    assert o.part("cb").doubles == "vc" and o.part("hn1").doubles == "vln1-a"
    assert o.part("vln1-a").doubles is None and o.part("vc").group == "low"
    assert o.reason.startswith("Low and warm")
    assert (o.velocity, o.cc1) == (VELOCITY, CC1) == (80, 80)


def test_unplayable_request_raises_a_clear_error():
    # Only the choir, on a 9th chord whose bass is its 5th: the four required tones (root, 3rd, 7th, 9th)
    # don't fit in three upper choir voices.
    chords = ex.chords(["C9/G"])
    with pytest.raises(GenerationError, match="C9/G"):
        generate(chords, Key("C", "major"), ensemble=Ensemble(frozenset({"choir"})))


def test_only_safe_mode_in_milestone_3():
    chords = ex.chords(["C"])
    with pytest.raises(ValueError):
        generate(chords, Key("C", "major"), mode="moderate")
