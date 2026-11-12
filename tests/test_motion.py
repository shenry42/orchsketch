"""Milestone 5 (motion): rhythm patterns, the melody and bass files, moderate mode, the independent bass and the
per-section sliders. Every new feature passes the same kind of sweep as Milestone 4's generator (no errors and no
generator_must_pass warnings), and the defaults still give exactly v0.4's notes."""
import json
import time
from dataclasses import replace
from pathlib import Path

import mido
import pytest

import checker_examples as ex
from make_v04_snapshot import note_digest, runs as v04_runs
from orchsketch import patterns as pat
from orchsketch.edits import regenerate, regenerate_chord, regenerate_part, swap
from orchsketch.export import export_part
from orchsketch.generator import (
    APPROACHES, DOUBLE_ID, MELODY_ID, Ensemble, GenerationError, Settings, colour_pcs, generate, generate_all,
    independent_bass, rerender,
)
from orchsketch.instruments import SECTIONS, instruments
from orchsketch.midi_io import BAR, Note, read_monophonic_file
from orchsketch.presets import builtin_presets, find
from orchsketch.theory import Key
from test_generator import COMBOS, EXPECTED, SLIDER_SAMPLE, load, must_fix

DATA = Path(__file__).parent / "data"
WITH_FILES = [e for e in EXPECTED if json.loads(e.read_text(encoding="utf-8")).get("melody_file")]
PATTERNS = pat.PATTERNS[1:]


def files_for(exp):
    base = exp.name.split(".")[0]
    mel = tuple(read_monophonic_file(DATA / f"{base}.melody.mid").notes)
    bass = tuple(read_monophonic_file(DATA / f"{base}.bass.mid").notes)
    return mel, bass


def walking_bass(chords) -> tuple[Note, ...]:
    """A bass line with passing tones: the chord's bass on beat 1, then steps (a stress test)."""
    out = []
    for c in chords:
        b = 36 + c.label.bass % 12
        t = c.start
        for k, step in enumerate((0, 2, 4, 5)):
            if t >= c.end:
                break
            out.append(Note(b + (step if k else 0), t, min(t + 480, c.end), 100))
            t += 480
    return tuple(out)


@pytest.fixture(scope="module", params=EXPECTED, ids=lambda p: p.name.split(".")[0])
def progression(request):
    return load(request.param)


def chord_at(chords, tick):
    return next(c for c in chords if c.start <= tick < c.end)


# ---------------------------------------------------------------- the defaults are v0.4
def test_defaults_give_exactly_the_v04_notes():
    """Sustain everywhere, safe mode, no melody or bass file: every note of A, B and C (pitch, rhythm,
    velocity) is exactly v0.4's, for every test file, preset line-up and Forces x Density sample."""
    snap = json.loads((DATA / "v04_snapshot.json").read_text(encoding="utf-8"))
    for rid, chords, key, a, ens in v04_runs(slider_approaches=("A",)):
        o = generate(chords, key, seed=1, approach=a, ensemble=ens)
        assert note_digest(o) == snap[rid], rid


def test_equal_section_values_are_the_master_values():
    chords, key = load(EXPECTED[0])
    a = generate(chords, key, seed=2, approach="B", ensemble=Ensemble(forces="divisi", density=3))
    ens = Ensemble(forces="section", density=5, section_forces={s: "divisi" for s in SECTIONS},
                   section_density={s: 3 for s in SECTIONS})
    b = generate(chords, key, seed=2, approach="B", ensemble=ens,
                 settings=Settings(section_dynamics={s: "mf" for s in SECTIONS}))
    assert a.cells == b.cells and [p.notes for p in a.parts] == [p.notes for p in b.parts]


# ---------------------------------------------------------------- patterns
def test_patterns_in_every_section(progression):
    """Each pattern on each section (rotated over the sweep), in A, B and C: pitches at every chord change stay
    the voicing's, notes stay inside their chord, and nothing breaks a rule."""
    chords, key = progression
    insts = instruments()
    for ai, a in enumerate(APPROACHES):
        base = generate(chords, key, seed=1, approach=a)
        for shift in range(len(PATTERNS)):
            sp = {sec: PATTERNS[(shift + ai + k) % len(PATTERNS)] for k, sec in enumerate(SECTIONS)}
            o = rerender(base, Settings(section_patterns=sp))
            assert not must_fix(o.report), (a, sp, o.report.text())
            assert o.cells == base.cells
            for p in o.parts:
                sec = insts[p.instrument].section
                for i, c in enumerate(chords):
                    here = [n for n in p.notes if c.start <= n.start < c.end]
                    if base.cells[p.id][i] is None:
                        assert not here
                        continue
                    first = min(here, key=lambda n: n.start)
                    tied = first.start < c.start
                    assert tied or first.start == c.start, (a, p.id, i)  # every pattern strikes the chord
                    assert first.pitch == base.cells[p.id][i] or tied
                    for n in here:
                        assert n.end <= c.end or sp[sec] == pat.SUSTAIN, (a, p.id, n)
                        assert insts[p.instrument].is_comfortable(n.pitch)
                        assert n.pitch % 12 in c.label.pcs() | {c.label.bass}  # safe: chord tones only


def test_every_pattern_everywhere_in_every_approach(progression):
    chords, key = progression
    for a in APPROACHES:
        base = generate(chords, key, seed=1, approach=a)
        for pt in PATTERNS:
            o = rerender(base, Settings(pattern=pt))
            assert not must_fix(o.report), (a, pt, o.report.text())
            assert not o.report.by_check("parallels"), (a, pt)  # patterns never add parallels at chord changes


def test_pattern_shapes():
    span = (0, BAR)
    eighths = pat.render(pat.EIGHTHS, 60, *span, 100)
    assert [(n.start, n.end) for n in eighths] == [(t, t + 240) for t in range(0, BAR, 240)]
    assert [n.velocity for n in eighths] == [100, 80, 80, 80, 100, 80, 80, 80]  # accents on 1 and 3
    alt = pat.render(pat.SIXTEENTHS_ALT, 67, *span, 100, alt=64)
    assert len(alt) == 16 and alt[0].pitch == 67 and alt[1].pitch == 64 and alt[-1].pitch == 67
    stabs = pat.render(pat.STABS, 60, 0, 2 * BAR, 100)
    assert [n.start for n in stabs] == [0, 720, BAR, BAR + 720] and all(n.length == 240 for n in stabs)
    half = pat.render(pat.HALF_TIME, 60, 240, BAR, 100)  # a chord starting on the "and" of 1 still strikes
    assert [n.start for n in half] == [240, 960]
    assert pat.passing_pitch(60, 64, Key("C", "major").scale_pcs()) == 62
    assert pat.passing_pitch(60, 62, Key("C", "major").scale_pcs()) is None
    assert [(n.start, n.end) for n in pat.split_at_bars([Note(60, 960, 2 * BAR + 480)])] == [
        (960, BAR), (BAR, 2 * BAR), (2 * BAR, 2 * BAR + 480)]


def test_part_and_instrument_patterns_and_choir_limits():
    chords, key = load(EXPECTED[0])
    base = generate(chords, key, seed=1)
    st = Settings(section_patterns={"choir": pat.SIXTEENTHS}, instrument_patterns={"tuba": pat.STABS},
                  part_patterns={"vc": pat.HALF_TIME})
    o = rerender(base, st)
    assert len(o.part("ch-s").notes) == len(base.part("ch-s").notes)  # a choir can't sing 16ths: sustains
    assert [n.start for n in o.part("tba").notes][:2] == [0, 720]
    assert [n.start for n in o.part("vc").notes][:2] == [0, 960]
    assert not must_fix(o.report)


def test_restrike_every_bar_and_ties():
    chords, key = ex.chords(["Am", "Am", "F", "F"]), Key("A", "minor")
    o = generate(chords, key, seed=1)
    assert [(n.start, n.end) for n in o.part("vc").notes] == [(0, 2 * BAR), (2 * BAR, 4 * BAR)]  # tied
    r = rerender(o, Settings(restrike_bars=True))
    assert [(n.start, n.end) for n in r.part("vc").notes] == [(k * BAR, (k + 1) * BAR) for k in range(4)]


def test_dynamics_per_section_set_velocity_and_cc1(tmp_path):
    chords, key = load(EXPECTED[0])
    o = rerender(generate(chords, key, seed=1), Settings(dynamics="p", section_dynamics={"brass": "ff"},
                                                          pattern=pat.EIGHTHS))
    assert {n.velocity for n in o.part("hn1").notes} == {120, 96}  # ff, unaccented 8ths at 80%
    assert {n.velocity for n in o.part("vc").notes} == {50, 40}  # p
    assert (o.cc1_for("hn1"), o.cc1_for("vc")) == (120, 50)
    path = export_part(o, "hn1", tmp_path, "T", 140, BAR * 4)
    cc = [m for m in mido.MidiFile(path).tracks[0] if m.type == "control_change"]
    assert cc[0].control == 1 and cc[0].value == 120


# ---------------------------------------------------------------- moderate mode
@pytest.mark.slow  # skipped by run_tests.bat; release.bat runs it
def test_moderate_mode_in_every_approach(progression):
    chords, key = progression
    insts = instruments()
    for a in APPROACHES:
        o = generate(chords, key, seed=1, approach=a, mode="moderate")
        assert o.mode == "moderate" and not must_fix(o.report), (a, o.report.text())
        assert not o.report.errors
        for p in o.parts:
            for n in p.notes:
                assert insts[p.instrument].is_playable(n.pitch)
                c = chord_at(chords, n.start)
                ok = c.label.pcs() | {c.label.bass} | colour_pcs(c.label, key)
                assert n.pitch % 12 in ok, (a, p.id, n, c.label)
        o2 = generate(chords, key, seed=1, approach=a, mode="moderate", settings=Settings(pattern=pat.EIGHTHS))
        assert not must_fix(o2.report), (a, o2.report.text())


def test_moderate_colour_tones_and_sections():
    total = coloured = 0
    for exp in EXPECTED[::2]:
        chords, key = load(exp)
        for a in APPROACHES:
            o = generate(chords, key, seed=1, approach=a, mode="moderate")
            for v, c in zip(o.meta["voices"], chords):
                total += 1
                coloured += any(p % 12 in colour_pcs(c.label, key) for k, p in v.items() if k.startswith("h"))
    assert 0.25 * total < coloured < 0.7 * total, (coloured, total)
    for combo in (COMBOS[0], COMBOS[2], COMBOS[-1]):
        chords, key = load(EXPECTED[10])
        for a in APPROACHES:
            o = generate(chords, key, seed=7, approach=a, mode="moderate", ensemble=Ensemble(combo))
            assert not must_fix(o.report), (sorted(combo), a, o.report.text())


def test_moderate_in_one_section_only():
    """Character per section: colour tones only in voices the moderate sections play alone; the safe
    sections keep chord tones and comfortable range."""
    insts = instruments()
    for exp in EXPECTED[::3]:
        chords, key = load(exp)
        for a in APPROACHES:
            st = Settings(section_character={"strings": "moderate"})
            o = generate(chords, key, seed=1, approach=a, settings=st)
            assert o.mode == "moderate" and not must_fix(o.report), (a, o.report.text())
            for p in o.parts:
                if insts[p.instrument].section == "strings":
                    continue
                for n in p.notes:
                    c = chord_at(chords, n.start)
                    assert insts[p.instrument].is_comfortable(n.pitch), (a, p.id, n)
                    assert n.pitch % 12 in c.label.pcs() | {c.label.bass}, (a, p.id, n)


def test_mixed_section_sliders_sweep(progression):
    chords, key = progression
    mixes = [
        Ensemble(section_density={"brass": 1, "woodwinds": 2}),
        Ensemble(section_forces={"strings": "divisi", "brass": "solo"}, section_density={"choir": 1}),
        Ensemble(forces="solo", section_forces={"strings": "section"}, density=3, section_density={"strings": 5}),
    ]
    for ens in mixes:
        for a in APPROACHES:
            o = generate(chords, key, seed=1, approach=a, ensemble=ens,
                         settings=Settings(section_character={"woodwinds": "moderate"}))
            assert not must_fix(o.report), (ens, a, o.report.text())


def test_section_density_thins_only_that_section():
    chords, key = load(EXPECTED[0])
    insts = instruments()
    full = generate(chords, key, seed=1)
    thin = generate(chords, key, seed=1, ensemble=Ensemble(section_density={"brass": 1}))

    def count(o, sec):
        return sum(insts[ln.instrument].section == sec for ln in o.sounding_lines)
    assert count(thin, "brass") < count(full, "brass")
    assert count(thin, "brass") >= 2  # still plays: one line per voice
    assert count(thin, "strings") == count(full, "strings")


# ---------------------------------------------------------------- melody and bass files (tests 1, 4, 11)
def test_test_files_with_melody_and_bass_are_1_4_and_11():
    assert [e.name.split("_")[0] for e in WITH_FILES] == ["01", "04", "11"]


@pytest.mark.slow  # skipped by run_tests.bat; release.bat runs it
@pytest.mark.parametrize("exp", WITH_FILES, ids=lambda p: p.name.split(".")[0])
def test_melody_and_bass_in_every_preset_and_approach(exp):
    chords, key = load(exp)
    mel, bass = files_for(exp)
    for seed, kind in ((1, {"melody": mel}), (2, {"bass": bass}), (2, {"melody": mel, "bass": bass})):
        for a in APPROACHES:
            o = generate(chords, key, seed=seed, approach=a, settings=Settings(**kind))
            assert not must_fix(o.report), (kind.keys(), a, o.report.text())
    for p in builtin_presets():
        for a in APPROACHES:
            st = Settings(p.ensemble(), melody=mel, bass=bass, dynamics=p.dynamics,
                          section_patterns=p.section_patterns(), instrument_patterns=p.instrument_patterns())
            o = generate(chords, key, seed=1, approach=a, settings=st)
            assert not must_fix(o.report), (p.id, a, o.report.text())
            _check_melody_and_bass(o, chords, mel, bass)
    for k, (forces, density) in enumerate(SLIDER_SAMPLE):
        for a in (APPROACHES[k % 3],):  # each sample once, approaches in turn
            o = generate(chords, key, seed=1, approach=a, ensemble=Ensemble(forces=forces, density=density),
                         settings=Settings(melody=mel, bass=bass, character="moderate", pattern=pat.EIGHTHS))
            assert not must_fix(o.report), (forces, density, a, o.report.text())


def _check_melody_and_bass(o, chords, mel, bass):
    """The melody is played exactly as written (rhythm and pitch, maybe at another octave), its doubling an
    octave from it, and every bass-file line plays the file's rhythm and pitch classes."""
    end = chords[-1].end
    want = [(n.start, min(n.end, end)) for n in mel if n.start < end]
    m = o.part(MELODY_ID)
    assert [(n.start, n.end) for n in m.notes] == want
    shift = m.notes[0].pitch - mel[0].pitch
    assert shift % 12 == 0 and all(a.pitch - b.pitch == shift for a, b in zip(m.notes, mel))
    if DOUBLE_ID in o.cells:
        d = o.part(DOUBLE_ID)
        assert [(n.start, n.end) for n in d.notes] == want
        assert {abs(a.pitch - b.pitch) for a, b in zip(d.notes, m.notes)} == {12}
    for lid in o.figures:
        if lid in (MELODY_ID, DOUBLE_ID):
            continue
        notes = o.part(lid).notes
        file_at = {n.start: n.pitch for n in bass if n.start < end}
        assert all(n.start in file_at and n.pitch % 12 == file_at[n.start] % 12 for n in notes), lid
        if len(notes) < len(file_at):  # v1.0: only an octave-below line rests on notes it can't reach, and it
            offsets = {n.pitch - file_at[n.start] for n in notes}  # never jumps an octave on its own
            assert len(offsets) == 1 and min(offsets) < 0, (lid, offsets)


@pytest.mark.parametrize("exp", WITH_FILES, ids=lambda p: p.name.split(".")[0])
def test_keep_as_is_with_melody_and_bass(exp):
    """Your kept voicing, melody and bass file together: everything the generator adds is clean; problems only
    between your own inputs (e.g. your voicing and your melody both on the leading tone) are shown."""
    from test_generator import load_with_voicings
    chords, key, voicings = load_with_voicings(exp)
    mel, bass = files_for(exp)
    insts = instruments()
    for a in APPROACHES:
        o = generate(chords, key, seed=1, approach=a, settings=Settings(keep=tuple(voicings), melody=mel, bass=bass))
        assert not must_fix(o.report, o.meta["fixed"]), (a, o.report.text())
        assert insts[o.line(MELODY_ID).instrument].section != "strings"  # the strings play your voicing


def test_melody_hosts_and_doubling():
    chords, key = load(EXPECTED[0])
    mel, _ = files_for(EXPECTED[0])
    alts = generate_all(chords, key, seed=1, settings=Settings(melody=mel))
    assert alts["B"].line(MELODY_ID).instrument == "violins_1"
    assert alts["C"].line(MELODY_ID).instrument == "flute"
    assert alts["A"].line(MELODY_ID).instrument == "violins_1"  # C5-A5 is too high for the horns (A's first pick)
    low = tuple(Note(n.pitch - 12, n.start, n.end) for n in mel)  # an octave down: the horns take it
    assert generate(chords, key, approach="A", settings=Settings(melody=low)).line(MELODY_ID).instrument == "horn"
    for a, o in alts.items():
        assert "melody in the" in o.reason
        assert DOUBLE_ID in o.cells  # Auto doubles at Density 5
    off = generate(chords, key, settings=Settings(melody=mel, melody_double="off"))
    assert DOUBLE_ID not in off.cells
    auto3 = generate(chords, key, ensemble=Ensemble(density=3), settings=Settings(melody=mel))
    assert DOUBLE_ID not in auto3.cells
    up = generate(chords, key, approach="A", settings=Settings(melody=mel, melody_double="up"))
    assert up.part(DOUBLE_ID).notes[0].pitch == up.part(MELODY_ID).notes[0].pitch + 12
    picked = generate(chords, key, settings=Settings(melody=mel, melody_instrument="oboe"))
    assert picked.line(MELODY_ID).instrument == "oboe"
    with pytest.raises(GenerationError, match="isn't playing"):
        generate(chords, key, ensemble=Ensemble(frozenset({"strings"})), settings=Settings(melody=mel, melody_instrument="oboe"))


def test_bass_lines_double_the_file_in_octaves():
    chords, key = load(EXPECTED[0])
    _, bass = files_for(EXPECTED[0])
    o = generate(chords, key, seed=1, settings=Settings(bass=bass))
    vc, cb = o.part("vc").notes, o.part("cb").notes
    assert [n.pitch for n in vc] == [n.pitch for n in bass]
    # basses an octave under the cellos; v1.0: a note they can't reach there rests instead of jumping up
    on = {n.start: n.pitch for n in vc}
    assert all(on[n.start] - n.pitch == 12 for n in cb) and len(cb) >= 6
    assert o.meta["info"]["bass"] == "file" and "bass line from your file" in o.reason


@pytest.mark.slow  # skipped by run_tests.bat; release.bat runs it
@pytest.mark.parametrize("exp", [EXPECTED[0], EXPECTED[7], EXPECTED[10]], ids=lambda p: p.name.split(".")[0])
def test_walking_bass_file_with_passing_tones(exp):
    chords, key = load(exp)
    bass = walking_bass(chords)
    mel, _ = files_for(EXPECTED[0]) if exp == EXPECTED[0] else (None, None)
    for p in builtin_presets():
        for a in APPROACHES:
            o = generate(chords, key, seed=1, approach=a, settings=Settings(p.ensemble(), bass=bass, melody=mel))
            assert not must_fix(o.report), (p.id, a, o.report.text())


# ---------------------------------------------------------------- independent bass (moderate only)
@pytest.mark.slow  # skipped by run_tests.bat; release.bat runs it
def test_independent_bass(progression):
    chords, key = progression
    scale = key.scale_pcs()
    line = independent_bass(chords, key)
    for n in line:
        c = chord_at(chords, n.start)
        assert n.pitch % 12 in scale | {c.label.bass}
    moved = 0
    for a in APPROACHES:
        o = generate(chords, key, seed=1, approach=a, mode="moderate", settings=Settings(independent_bass=True))
        assert not must_fix(o.report), (a, o.report.text())
        assert o.meta["info"].get("bass") == "independent"
        moved += len(o.part("vc").notes) > len(chords) if "vc" in o.cells else 0
        # safe mode ignores the toggle
        s = generate(chords, key, seed=1, approach=a, settings=Settings(independent_bass=True))
        assert "bass" not in s.meta["info"]
    if any(n.pitch % 12 != chord_at(chords, n.start).label.bass for n in line):  # it has passing notes
        assert moved, "the independent bass never moved"


# ---------------------------------------------------------------- edits with files and patterns
def test_edits_with_melody_bass_and_patterns():
    chords, key = load(EXPECTED[10])
    mel, bass = files_for(EXPECTED[10])
    st = Settings(melody=mel, bass=bass, pattern=pat.EIGHTHS, character="moderate")
    alts = generate_all(chords, key, seed=1, settings=st)
    a = alts["A"]
    assert not must_fix(a.report)
    with pytest.raises(GenerationError, match="as written"):
        regenerate_part(a, MELODY_ID)
    with pytest.raises(GenerationError, match="as written"):
        regenerate_part(a, "vc")
    r = regenerate(a, frozenset({"vln1-b"}))
    assert r.cells["vln1-b"] == a.cells["vln1-b"] and r.part(MELODY_ID).notes == a.part(MELODY_ID).notes
    assert not must_fix(r.report)
    c = regenerate_chord(a, 3)
    assert c.part(MELODY_ID).notes == a.part(MELODY_ID).notes and not must_fix(c.report)
    hn = next(ln.id for ln in a.sounding_lines if ln.id == "hn2")
    p = regenerate_part(a, hn)
    assert p.cells[hn] != a.cells[hn]
    s = swap(a, alts["B"], [2])
    assert s.sources[2] == "B"
    assert s.part("vc").notes  # the bass file still plays
    # patterns and dynamics re-render without regenerating
    q = rerender(a, replace(a.settings, pattern=pat.HALF_TIME, dynamics="ff"))
    assert q.cells == a.cells and q.part(MELODY_ID).notes[0].velocity == 120


def test_everything_at_once_is_quick():
    chords, key = load(EXPECTED[10])  # 16 bars, 24 chords
    mel, bass = files_for(EXPECTED[10])
    st = Settings(melody=mel, bass=bass, character="moderate", section_patterns={"strings": pat.SIXTEENTHS_ALT},
                  instrument_patterns={"tuba": pat.STABS})
    t = time.perf_counter()
    alts = generate_all(chords, key, seed=1, settings=st)
    assert time.perf_counter() - t < 15
    assert all(not must_fix(o.report) for o in alts.values())


@pytest.mark.parametrize("exp", [EXPECTED[0], EXPECTED[2], EXPECTED[6]], ids=lambda p: p.name.split(".")[0])
def test_regenerate_does_not_cycle_back(exp):
    """Regenerate unlocked avoids every earlier variation in the chain (Sam: it used to bounce between two)."""
    chords, key = load(exp)
    o = generate(chords, key, seed=1)
    seen = []
    for _ in range(8):
        seen.append(tuple(map(tuple, o.cells.values())))
        o = regenerate(o)
        assert not must_fix(o.report)
    assert len(set(seen)) == 8


# ---------------------------------------------------------------- v1.0 test-set fixes
@pytest.mark.parametrize("approach", APPROACHES)
def test_low_bass_lines_keep_the_file_shape(approach):
    """v1.0 (Sam's ear test, test 11 + files): tuba, basses and contrabassoon play the bass file an octave down
    and rest on the notes they can't reach there, instead of jumping up an octave on their own notes."""
    chords, key = load(EXPECTED[10])
    mel, bass = files_for(EXPECTED[10])
    o = generate(chords, key, seed=1, approach=approach, settings=Settings(melody=mel, bass=bass))
    assert not must_fix(o.report, set(o.meta["fixed"]))
    file_at = {n.start: n.pitch for n in bass}
    for lid in ("cb", "tba", "cbn"):
        if lid not in o.cells or not o.part(lid).notes:
            continue
        offsets = {n.pitch - file_at[n.start] for n in o.part(lid).notes if n.start in file_at}
        assert len(offsets) == 1, (lid, offsets)  # one octave for the whole line: never a jump of its own


def test_melody_in_a_choir_voice_is_a_choir_voice():
    """v1.0 (Sam): a melody given to the choir altos counts as a choir voice in the search (no parallels with
    the other choir parts), and clashes only between your own melody and bass files are shown, not refused."""
    for exp in WITH_FILES:
        chords, key = load(exp)
        mel, bass = files_for(exp)
        for b in (None, bass):
            st = Settings(melody=mel, bass=b, melody_instrument="choir_alto", character="moderate")
            for a in APPROACHES:
                o = generate(chords, key, seed=1, approach=a, settings=st)
                assert o.part(MELODY_ID).notes and o.line("mel").instrument == "choir_alto"
                assert not must_fix(o.report, set(o.meta["fixed"])), (exp.name, a, b is not None)
    chords, key = load(EXPECTED[10])
    mel, _ = files_for(EXPECTED[10])
    with pytest.raises(GenerationError, match="choir bass can't go low enough.*Moderate"):
        generate(chords, key, seed=1, settings=Settings(melody=mel, melody_instrument="choir_alto"))
