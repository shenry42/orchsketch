"""Generator: approaches A, B and C orchestrate every test progression with no checker errors and no
generator_must_pass warnings, in every section combination, every preset and across the sliders,
deterministically per seed. Approach A at the default settings is exactly Milestone 3's result."""
import json
from itertools import combinations
from pathlib import Path

import pytest

import checker_examples as ex
from orchsketch.analysis import AnalysisSession
from orchsketch.checker import check, chords_from_session
from orchsketch.generator import (
    APPROACHES, CC1, VELOCITY, Ensemble, GenerationError, Settings, approach_lines, generate, generate_all,
    with_dynamics,
)
from orchsketch.instruments import SECTIONS, instruments
from orchsketch.midi_io import read_chord_file
from orchsketch.presets import builtin_presets, find
from orchsketch.rules import rules
from orchsketch.theory import Key

DATA = Path(__file__).parent / "data"
EXPECTED = sorted(DATA.glob("*.expected.json"))
COMBOS = [frozenset(c) for n in range(1, 5) for c in combinations(SECTIONS, n)]
SLIDER_SAMPLE = [("solo", 1), ("solo", 5), ("section", 2), ("section", 4), ("divisi", 3), ("divisi", 5)]


def load(exp_path):
    exp = json.loads(exp_path.read_text(encoding="utf-8"))
    key = Key(exp["key"]["tonic"], exp["key"]["mode"])
    s = AnalysisSession(read_chord_file(DATA / exp["file"]), key)
    assert s.confirm_all() == 0
    return chords_from_session(s), key


def load_with_voicings(exp_path):
    exp = json.loads(exp_path.read_text(encoding="utf-8"))
    key = Key(exp["key"]["tonic"], exp["key"]["mode"])
    s = AnalysisSession(read_chord_file(DATA / exp["file"]), key)
    s.confirm_all()
    return chords_from_session(s), key, [tuple(sorted(r.segment.pitches)) for r in s.chord_results]


def must_fix(report, owned=frozenset()):
    r = rules()
    return [i for i in report.issues if (i.severity == "error" or r.checks[i.check].generator_must_pass)
            and not (i.parts and set(i.parts) <= owned)]


@pytest.fixture(scope="module", params=EXPECTED, ids=lambda p: p.name.split(".")[0])
def progression(request):
    return load(request.param)


def test_a_is_unchanged_from_milestone_3():
    """Approach A at the default settings: every run of the Milestone 3 sweep gives the same notes."""
    from make_a_snapshot import digest, runs
    snap = json.loads((DATA / "a_v03_snapshot.json").read_text(encoding="utf-8"))
    for rid, chords, key, seed, combo in runs():
        o = generate(chords, key, seed=seed, ensemble=Ensemble(combo) if combo else None)
        assert digest(o) == snap[rid], rid
        assert not o.report.issues, (rid, o.report.text())  # no errors and no warnings of any kind
        assert not must_fix(check(o.parts, chords, key, "safe")), rid  # re-check independently


@pytest.mark.parametrize("approach", ["B", "C"])
def test_b_and_c_are_clean_in_every_section_combination(progression, approach):
    chords, key = progression
    for seed in (1, 2, 3):
        o = generate(chords, key, seed=seed, approach=approach)
        assert not o.report.issues, (seed, o.report.text())
        assert not must_fix(check(o.parts, chords, key, "safe")), o.report.text()
    for combo in COMBOS:
        o = generate(chords, key, seed=7, approach=approach, ensemble=Ensemble(combo))
        assert not o.report.issues, (sorted(combo), o.report.text())
        assert {instruments()[ln.instrument].section for ln in o.sounding_lines} == set(combo)


def test_every_preset_in_every_approach(progression):
    chords, key = progression
    for p in builtin_presets():
        for a in APPROACHES:
            o = generate(chords, key, seed=1, approach=a, ensemble=p.ensemble())
            assert not must_fix(o.report), (p.id, a, o.report.text())
            assert {ln.instrument for ln in o.sounding_lines} <= set(p.instruments)


def test_forces_and_density_sliders(progression):
    chords, key = progression
    for forces, density in SLIDER_SAMPLE:
        for a in APPROACHES:
            o = generate(chords, key, seed=1, approach=a, ensemble=Ensemble(forces=forces, density=density))
            assert not must_fix(o.report), (forces, density, a, o.report.text())


def test_safe_mode_stays_in_comfortable_range_and_uses_chord_tones(progression):
    chords, key = progression
    insts = instruments()
    for a in APPROACHES:
        o = generate(chords, key, seed=1, approach=a)
        for p in o.parts:
            for n in p.notes:
                assert insts[p.instrument].is_comfortable(n.pitch), (a, p.id, n)
                span = next(c for c in chords if c.start <= n.start < c.end)
                assert n.pitch % 12 in span.label.pcs() | {span.label.bass}, (a, p.id, n, span.label)
                assert n.velocity == VELOCITY


def test_follow_input_puts_the_clip_top_note_on_top():
    matched = total = 0
    for exp in EXPECTED:
        chords, key, voicings = load_with_voicings(exp)
        tops = tuple(max(v) for v in voicings)
        for a in APPROACHES:
            o = generate(chords, key, seed=1, approach=a, settings=Settings(top_voice="input", tops=tops))
            assert not must_fix(o.report), (exp.name, a, o.report.text())
            for v, top in zip(o.meta["voices"], tops):
                highest = max(p for name, p in v.items() if name.startswith("h"))
                total += 1
                matched += highest % 12 == top % 12
    assert matched >= 0.95 * total, (matched, total)


@pytest.mark.parametrize("preset", ["full_epic", "strings_horns", "low_heavy", "strings_only"])
def test_keep_as_is_keeps_the_input_voicing_exactly(preset):
    p = find(builtin_presets(), preset)
    insts = instruments()
    for exp in EXPECTED:
        chords, key, voicings = load_with_voicings(exp)
        for a in APPROACHES:
            o = generate(chords, key, seed=1, approach=a, settings=Settings(p.ensemble(), keep=tuple(voicings)))
            fixed = o.meta["fixed"]
            assert not must_fix(o.report, fixed), (exp.name, a, o.report.text())
            for i, v in enumerate(voicings):
                kept = sorted(o.cells[lid][i] for lid in fixed if o.cells[lid][i] is not None)
                assert kept == sorted(set(v)), (exp.name, i)
            # the regular string lines don't play: the strings are yours
            assert not any(insts[ln.instrument].section == "strings" and ln.id not in fixed
                           for ln in o.sounding_lines)
            assert o.reason.split(": ", 1)[1].startswith("your voicing kept")


def test_alternatives_differ_in_the_promised_direction():
    chords, key = load(EXPECTED[10])  # 16 bars
    alts = generate_all(chords, key, seed=1)

    def stats(o):
        tops, spans = [], []
        for i in range(len(chords)):
            ps = [o.cells[ln.id][i] for ln in o.lines if o.cells[ln.id][i] is not None]
            tops.append(max(ps))
            spans.append(max(ps) - min(ps))
        return sum(tops) / len(tops), sum(spans) / len(spans)

    (a_top, a_span), (b_top, b_span), (c_top, c_span) = (stats(alts[x]) for x in APPROACHES)
    assert b_span > a_span + 6  # B is the widest
    assert c_top > a_top + 6  # C is high and bright
    assert alts["A"].cells != alts["B"].cells != alts["C"].cells
    for x, name in zip(APPROACHES, ("Low and warm", "Wide and full", "High and bright")):
        assert alts[x].reason.startswith(name) and alts[x].approach == x
    assert "picc" in {ln.id for ln in alts["C"].sounding_lines} and "tpt3" in {ln.id for ln in alts["C"].sounding_lines}
    assert "tba" not in {ln.id for ln in alts["C"].sounding_lines}  # C: lighter bass


def test_same_seed_same_result_and_seeds_vary():
    chords, key = load(EXPECTED[10])  # 16 bars
    for a in APPROACHES:
        x = generate(chords, key, seed=5, approach=a)
        y = generate(chords, key, seed=5, approach=a)
        assert x.cells == y.cells and [p.notes for p in x.parts] == [p.notes for p in y.parts]
    results = {tuple(map(tuple, generate(chords, key, seed=s).cells.values())) for s in range(1, 7)}
    assert len(results) > 1


def test_density_and_forces_change_the_lines():
    insts = instruments()
    A = __import__("orchsketch.generator", fromlist=["APPROACH"]).APPROACH["A"]
    counts = [len(approach_lines(A, Ensemble(density=d), insts)) for d in (1, 2, 3, 4, 5)]
    assert counts == sorted(counts) and counts[0] < counts[-1]
    solo = {ln.id for ln in approach_lines(A, Ensemble(forces="solo"), insts)}
    divisi = {ln.id for ln in approach_lines(A, Ensemble(forces="divisi"), insts)}
    assert {"vln1-solo", "vc-solo"} <= solo and not {"vln1-a", "vln1-b", "hn1"} & solo
    assert {"vln2-a", "vln2-b", "vla-a", "vla-b", "vc-a", "vc-b"} <= divisi and "vln2" not in divisi


def test_dynamics_change_velocity_and_cc1_only():
    chords, key = load(EXPECTED[0])
    o = generate(chords, key, seed=1)
    f = with_dynamics(o, "ff")
    assert (f.velocity, f.cc1) == (120, 120) and f.cells == o.cells
    assert all(n.velocity == 120 for p in f.parts for n in p.notes)
    p = generate(chords, key, seed=1, settings=Settings(dynamics="pp"))
    assert p.cells == o.cells and (p.velocity, p.cc1) == (30, 30)


def test_three_alternatives_are_quick():
    import time
    chords, key = load(EXPECTED[10])  # 16 bars, 24 chords
    t = time.perf_counter()
    generate_all(chords, key, seed=1)
    assert time.perf_counter() - t < 12  # about 2 s on the build machine; runs in the background in the app


def test_notes_sustain_for_the_chord_and_tie_over_repeated_chords():
    chords, key = ex.chords(["Am", "Am", "F", "F"]), Key("A", "minor")
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
    for a in APPROACHES:
        with pytest.raises(GenerationError, match="C9/G"):
            generate(chords, Key("C", "major"), approach=a, ensemble=Ensemble(frozenset({"choir"})))


def test_mode_must_be_safe_or_moderate():
    chords = ex.chords(["C"])
    with pytest.raises(ValueError):
        generate(chords, Key("C", "major"), mode="wild")  # wild mode is reserved for later (SPEC §6)
