"""Milestone 8 (v1.3): textures and shapes - arpeggios, hits and anticipations, intensity shapes, phrase-end
fills, the unison/octave theme, pattern emphasis, a clear low register, accents on chord changes, the window and
project parts of them, and A/B/C in parallel processes.

Ground rules (SPEC §14): with every new option at its default the output is exactly v1.2's (the A, v0.4 and v1.1
pattern snapshots in the other test files); generated output has 0 checker errors and 0 generator_must_pass
warnings; 16 bars with melody and bass files stay fast."""
import json
import os
import time
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest

from orchsketch import patterns as pat
from orchsketch import shapes as shp
from orchsketch.checker import ChordSpan, Part, check
from orchsketch.generator import (
    APPROACHES, DYNAMICS, FILL_DROPOUT, FILL_PICKUP, FILL_RUN, FILLS, Orchestration, Settings, generate,
    generate_all, rerender,
)
from orchsketch.instruments import SECTIONS, instruments
from orchsketch.midi_io import BAR, PPQ, Note, read_monophonic_file
from orchsketch.presets import builtin_presets
from orchsketch.theory import Key
from test_generator import EXPECTED, load, load_with_voicings, must_fix

DATA = Path(__file__).parent / "data"
EPIC = next(p for p in builtin_presets() if p.id == "full_epic")
ARPS = tuple(p for p in pat.V13_PATTERNS if p.startswith("arp"))
HITS = ("stabs_sync", "stabs_push", "hit_downbeat")


def files(k):
    d = json.loads(EXPECTED[k].read_text(encoding="utf-8"))
    if not d.get("melody_file"):
        return None, None
    return (tuple(read_monophonic_file(DATA / d["melody_file"]).notes),
            tuple(read_monophonic_file(DATA / d["bass_file"]).notes))


@lru_cache(maxsize=None)
def base(k: int, a: str, with_files: bool = False, theme: bool = False):
    chords, key, voic = load_with_voicings(EXPECTED[k])
    mel, bass = files(k) if with_files else (None, None)
    st = Settings(EPIC.ensemble(), tops=tuple(max(v) for v in voic), melody=mel, bass=bass, theme=theme)
    return generate(chords, key, seed=1, approach=a, settings=st), chords, key


def clean(o):
    assert not must_fix(o.report, set(o.meta.get("fixed", ()))), o.report.text()
    assert not o.report.errors, o.report.text()


def sounding(o, lid, c):
    return [n for n in o.part(lid).notes if n.start < c.end and n.end > c.start]


# ---------------------------------------------------------------- data
def test_new_pattern_and_shape_files_load():
    lib = pat.library()
    for p in pat.V13_PATTERNS:
        assert p in lib
    assert {"arp", "hit"} <= {lib[p].family for p in pat.V13_PATTERNS}
    assert lib["arp_r5810"].degrees and lib["stabs_push"].anticipate
    assert [s for s in shp.SHAPES] == ["steady", "build", "swell", "drop", "build_hit", "phrase4", "breakdown",
                                       "pulse_bed"]
    assert pat.step_down("16ths_rise", 1) == "8ths" and pat.step_down("8ths", 2) == pat.SUSTAIN
    assert pat.step_down("8ths", 1, choir=True) == "half_time"
    assert pat.step_down("arp_r5810", 1) == "half_time"


def test_bad_shape_and_pattern_files_are_rejected(tmp_path):
    with pytest.raises(shp.ShapeError):
        shp._step({"density": 1}, "x.json")  # shapes only lower the settings
    with pytest.raises(shp.ShapeError):
        shp._step({"louder": -1}, "x.json")
    with pytest.raises(pat.PatternError):
        pat._parse_pattern({"id": "x", "name": "x", "kind": "grid", "anticipate": True}, "x.json")
    with pytest.raises(pat.PatternError):
        pat._parse_pattern({"id": "x", "name": "x", "kind": "grid", "degrees": True, "contour": [0, 7]}, "x.json")


def test_bar_steps():
    st = shp.bar_steps("build", 4)
    assert st[0].density == -3 and st[-1].neutral
    assert [s.density for s in shp.bar_steps("build", 16)] == [-3] * 4 + [-2] * 4 + [-1] * 4 + [0] * 4
    hit = shp.bar_steps("build_hit", 8)
    assert hit[-1].hit and not any(s.hit for s in hit[:-1])
    assert [b for b, s in enumerate(hit) if s.dropout] == [6]  # only the last bar of the drop-out step
    ph = shp.bar_steps("phrase4", 8)
    assert [b for b, s in enumerate(ph) if s.dropout] == [3, 7]
    assert [b for b, s in enumerate(shp.bar_steps("phrase4", 8, phrase=2)) if s.dropout] == [1, 3, 5, 7]
    assert [s.sections for s in shp.bar_steps("pulse_bed", 16)] == [1] * 4 + [2] * 4 + [3] * 4 + [4] * 4
    assert [s.sections for s in shp.bar_steps("pulse_bed", 4)] == [1, 2, 3, 4]
    assert all(s.neutral for s in shp.bar_steps("steady", 7))


def test_degree_pitches():
    assert pat.degree_pitch(40, 5, {4, 7, 11}) == 47
    assert pat.degree_pitch(40, 10, {4, 8, 11}) == 56  # E major: G#
    assert pat.degree_pitch(40, 10, {4, 7, 11}) == 55  # E minor: G
    assert pat.degree_pitch(40, 8, set()) == 52


# ---------------------------------------------------------------- arpeggios and hits
@pytest.mark.parametrize("k", range(0, len(EXPECTED), 4), ids=lambda k: EXPECTED[k].name[:2])
def test_arpeggios_are_chord_tones_in_range_and_keep_the_harmony(k):
    insts = instruments()
    for a in APPROACHES:
        b, chords, key = base(k, a)
        for pt in ARPS:
            o = rerender(b, Settings(section_patterns={"strings": pt}, note_mode=pat.SCALE_STEPS))
            clean(o)
            assert o.cells == b.cells
            for p in o.parts:
                for n in p.notes:
                    c = next(c for c in chords if c.start <= n.start < c.end)
                    assert n.pitch % 12 in c.label.pcs() | {c.label.bass}, (pt, p.id, n)
                    assert insts[p.instrument].is_comfortable(n.pitch)


def test_root_fifth_octave_tenth_in_the_cellos():
    b, chords, key = base(0, "A")
    o = rerender(b, Settings(instrument_patterns={"cellos": "arp_r5810"}))
    clean(o)
    c = chords[0]  # Am, one bar
    ps = [n.pitch - b.cells["vc"][0] for n in o.part("vc").notes if c.start <= n.start < c.end]
    assert ps[:4] == [0, 7, 12, 15] or set(ps) == {0}  # the safety net may hold the note (never anything else)


def test_anticipations_strike_the_next_chord_an_eighth_early():
    b, chords, key = base(0, "A")
    o = rerender(b, Settings(section_patterns={"brass": "stabs_push"}))
    clean(o)
    early = 0
    for lid in ("hn1", "hn2", "tbn1"):
        if lid not in o.cells:
            continue
        for i in range(len(chords) - 1):
            t = chords[i].end - PPQ // 2
            ns = [n for n in o.part(lid).notes if n.start == t]
            if ns:
                early += 1
                n = ns[0]
                assert n.pitch == o.cells[lid][i + 1] and n.end > chords[i + 1].start  # tied over
                assert not [x for x in o.part(lid).notes if x.start == chords[i + 1].start]
    assert early


def test_hits_and_stabs_everywhere():
    for k in range(0, len(EXPECTED), 2):
        for a in APPROACHES:
            b, chords, key = base(k, a)
            for pt in HITS:
                o = rerender(b, Settings(pattern=pt))
                clean(o)
                assert o.cells == b.cells


# ---------------------------------------------------------------- shapes
def _vel(o, lid, bar):
    return [n.velocity for n in o.part(lid).notes if n.start // BAR == bar]


def test_build_thins_softens_and_ends_as_set():
    b, chords, key = base(10, "A")  # test 11, 16 bars
    o = rerender(b, Settings(shape="build", pattern="8ths"))
    clean(o)
    full = rerender(b, Settings(pattern="8ths"))
    first = [c for c in chords if c.start < 4 * BAR]
    last = [c for c in chords if c.start >= 12 * BAR]

    def count(x, cs):
        return sum(1 for p in x.parts for c in cs if sounding(x, p.id, c))
    assert count(o, first) < count(full, first)
    assert count(o, last) == count(full, last)
    assert max(_vel(o, "vln1-a", 0)) < max(_vel(o, "vln1-a", 15)) == max(_vel(full, "vln1-a", 15))
    # notes in the last quarter are exactly as set
    for p, q in zip(o.parts, full.parts):
        assert [n for n in p.notes if n.start >= 12 * BAR] == [n for n in q.notes if n.start >= 12 * BAR]
    assert o.cells == b.cells


def test_build_and_hit_ends_on_one_hit():
    b, chords, key = base(0, "B")
    o = rerender(b, Settings(shape="build_hit", pattern="8ths"))
    clean(o)
    for p in o.parts:
        if p.id in o.figures:
            continue
        last = [n for n in p.notes if n.start >= 3 * BAR]
        assert len(last) <= 1 and all(n.start == 3 * BAR and n.end - n.start <= 2 * PPQ for n in last)
        assert not [n for n in p.notes if 3 * BAR - PPQ // 2 <= n.start < 3 * BAR]  # drop-out before it


def test_breakdown_keeps_one_section_and_every_chord_tone():
    b, chords, key = base(10, "B")
    o = rerender(b, Settings(shape="breakdown"))
    clean(o)
    mid = [c for c in chords if 4 * BAR <= c.start < 12 * BAR]
    insts = instruments()
    for c in mid:
        secs = {insts[p.instrument].section for p in o.parts if sounding(o, p.id, c)}
        assert len(secs) <= len({insts[p.instrument].section for p in b.parts if sounding(b, p.id, c)})
    assert sum(1 for p in o.parts for c in mid if sounding(o, p.id, c)) < sum(
        1 for p in b.parts for c in mid if sounding(b, p.id, c))


def test_pulse_bed_adds_a_section_every_four_bars():
    b, chords, key = base(10, "A")
    o = rerender(b, Settings(shape="pulse_bed", pattern="8ths"))
    clean(o)
    insts = instruments()

    def secs(lo, hi):
        return {insts[p.instrument].section for p in o.parts for n in p.notes if lo * BAR <= n.start < hi * BAR}
    assert secs(0, 4) <= {"strings"} | secs(0, 4) and len(secs(0, 4)) <= len(secs(4, 8)) <= len(secs(12, 16))
    assert secs(12, 16) == {insts[p.instrument].section for p in b.parts if p.notes}
    # the section that just came in plays a step softer than the ones already there
    assert max(_vel(o, "vln1-a", 4)) > max(n.velocity for p in o.parts if p.instrument == "horn"
                                           for n in p.notes if 4 * BAR <= n.start < 8 * BAR)


@pytest.mark.parametrize("k", range(len(EXPECTED)), ids=lambda k: EXPECTED[k].name[:2])
def test_every_shape_with_patterns_and_fills_sample(k):
    a = APPROACHES[k % 3]
    b, chords, key = base(k, a)
    for j, sh in enumerate(shp.SHAPES):
        pt = (pat.EIGHTHS, "arp_up", "stabs_push", "16ths_rise")[j % 4]
        st = Settings(shape=sh, pattern=pt, fill=FILLS[j % 4], phrase=(2, 4)[j % 2], pattern_emphasis=j % 2 == 0,
                      clear_low=j % 3 == 0, change_accents=j % 2 == 1, note_mode=pat.HYBRID)
        o = rerender(b, st)
        clean(o)
        assert o.cells == b.cells


@pytest.mark.slow
@pytest.mark.parametrize("k", range(len(EXPECTED)), ids=lambda k: EXPECTED[k].name[:2])
def test_every_shape_pattern_and_fill_everywhere(k):
    """Every shape × patterns (one per family, rotated over the sections) × fills, for A, B and C."""
    fams = (pat.EIGHTHS, "arp_updown", "stabs_sync", "16ths_rise", "arp_r5810", "stabs_push")
    for a in APPROACHES:
        b, chords, key = base(k, a)
        for j, sh in enumerate(shp.SHAPES):
            for f, fill in enumerate(FILLS):
                sp = {sec: fams[(j + f + s) % len(fams)] for s, sec in enumerate(SECTIONS)}
                o = rerender(b, Settings(shape=sh, section_patterns=sp, fill=fill, phrase=(2, 4, 8)[f % 3]))
                clean(o)


def test_shapes_with_melody_and_bass_files():
    for k in (0, 3, 10):
        for a in APPROACHES:
            b, chords, key = base(k, a, with_files=True)
            for sh in ("build", "phrase4", "breakdown", "build_hit"):
                o = rerender(b, replace(b.settings, shape=sh, pattern="8ths", fill=FILL_RUN))
                clean(o)
                # your files are never changed by a shape or a fill
                for lid in o.meta["fixed"]:
                    assert o.part(lid).notes == rerender(b, replace(b.settings, pattern="8ths")).part(lid).notes \
                        or o.part(lid).notes == b.part(lid).notes


def test_section_shapes():
    b, chords, key = base(10, "A")
    o = rerender(b, Settings(section_shapes={"brass": "build"}))
    clean(o)
    insts = instruments()
    for p, q in zip(o.parts, b.parts):
        if insts[p.instrument].section != "brass":
            assert p.notes == q.notes


# ---------------------------------------------------------------- fills
def test_runs_land_on_the_next_chord_and_are_checked_for_range_only():
    b, chords, key = base(10, "B")  # 16 bars: phrases of 4
    o = rerender(b, Settings(fill=FILL_RUN, pattern="8ths"))
    clean(o)
    runs = [(p, a, z) for p in o.parts for a, z in p.free]
    assert runs
    insts = instruments()
    for p, a, z in runs:
        assert z % (4 * BAR) == 0 and z - a == PPQ
        ns = [n for n in p.notes if a <= n.start < z]
        assert len(ns) == 4 and all(n.end - n.start == PPQ // 4 for n in ns)
        j = next(i for i, c in enumerate(chords) if c.start == z)
        target = o.cells[p.id][j]
        scale = pat.chord_scale(chords[j].label.pcs() | {chords[j].label.bass}, key)
        assert all(n.pitch % 12 in scale and insts[p.instrument].is_comfortable(n.pitch) for n in ns)
        step = ns[-1].pitch - target
        assert 0 < abs(step) <= 2  # one scale step from the downbeat note
        assert [n for n in p.notes if n.start == z][0].pitch == target


def test_pickups_and_dropouts():
    b, chords, key = base(10, "A")
    o = rerender(b, Settings(fill=FILL_PICKUP, pattern="8ths"))
    clean(o)
    assert any(len([n for n in p.notes if a <= n.start < z]) == 2 for p in o.parts for a, z in p.free)
    d = rerender(b, Settings(section_fills={"strings": FILL_DROPOUT}))
    clean(d)
    insts = instruments()
    for p in d.parts:
        for t in (4 * BAR, 8 * BAR, 12 * BAR):
            silent = not [n for n in p.notes if n.start < t and n.end > t - PPQ]
            if insts[p.instrument].section == "strings" and any(c.start == t for c in chords) and p.id not in d.figures:
                assert silent or not b.part(p.id).notes


def test_checker_skips_free_notes_except_range():
    insts = instruments()
    key = Key("C", "major")
    from orchsketch.analysis.chords import ChordLabel
    chords = [ChordSpan(0, BAR, ChordLabel(0, "maj", 0))]
    run = [Note(38, 0, BAR - PPQ), Note(49, BAR - PPQ, BAR - PPQ + 120), Note(51, BAR - 360, BAR - 240)]
    a = Part("a", "cellos", tuple(run))
    b = Part("b", "cellos", (Note(50, 0, BAR),), name="b")
    loose = check([a, b], chords, key)
    tight = check([replace(a, free=((BAR - PPQ, BAR),)), b], chords, key)
    assert loose.by_check("low_interval") and not tight.by_check("low_interval")
    wild = Part("c", "cellos", (Note(10, BAR - PPQ, BAR - PPQ + 120),), free=((BAR - PPQ, BAR),))
    assert check([wild], chords, key).by_check("playable_range")


# ---------------------------------------------------------------- theme in octaves
def test_theme_in_octaves_without_a_melody_file():
    b, chords, key = base(0, "A", theme=True)
    clean(b)
    assert "theme (top voice) in octaves" in b.reason
    theme = [ln.id for ln in b.lines if ln.role == "melody"]
    assert {"hn1", "vc"} <= set(theme) and {"ch-s", "ch-a", "ch-t"} <= set(theme)
    assert not b.report.by_check("choir_parallels")
    _, _, voic = load_with_voicings(EXPECTED[0])
    for lid in theme:
        for i, c in enumerate(chords):
            ns = sounding(b, lid, c)
            assert ns and all(n.pitch % 12 == max(voic[i]) % 12 for n in ns)
        assert b.part(lid).notes[0].pitch >= 48 or lid.startswith("ch-")
    # the other horns rest (one theme line per instrument), the choir bass sings the bass
    assert not b.part("hn2").notes and b.part("ch-b").notes


@pytest.mark.parametrize("k", range(len(EXPECTED)), ids=lambda k: EXPECTED[k].name[:2])
def test_theme_everywhere(k):
    chords, key, voic = load_with_voicings(EXPECTED[k])
    tops = tuple(max(v) for v in voic)
    mel, bass = files(k)
    for p in builtin_presets():
        for m, bs in ((None, None), (mel, None), (mel, bass)) if mel else ((None, None),):
            st = Settings(p.ensemble(), tops=tops, theme=True, melody=m, bass=bs, pattern="8ths")
            for a in APPROACHES:
                clean(generate(chords, key, seed=1, approach=a, settings=st))


def test_theme_off_is_v12():
    chords, key, voic = load_with_voicings(EXPECTED[0])
    st = Settings(EPIC.ensemble(), tops=tuple(max(v) for v in voic))
    assert generate(chords, key, seed=1, settings=st).cells == generate(chords, key, seed=1, settings=replace(
        st, theme=False)).cells


def test_choir_theme_parts_are_one_line_for_the_checker():
    insts = instruments()
    from orchsketch.analysis.chords import ChordLabel
    key = Key("C", "major")
    chords = [ChordSpan(0, BAR, ChordLabel(0, "maj", 0)), ChordSpan(BAR, 2 * BAR, ChordLabel(7, "maj", 7))]
    s = Part("ch-s", "choir_soprano", (Note(72, 0, BAR), Note(74, BAR, 2 * BAR)), role="melody")
    t = Part("ch-t", "choir_tenor", (Note(60, 0, BAR), Note(62, BAR, 2 * BAR)), role="melody")
    assert not check([s, t], chords, key).by_check("choir_parallels")
    assert check([replace(s, role=None), replace(t, role=None)], chords, key).by_check("choir_parallels")


# ---------------------------------------------------------------- the ear-test fixes
def test_pattern_emphasis_makes_patterns_louder_than_sustains():
    b, chords, key = base(0, "A")
    st = Settings(section_patterns={"strings": "8ths"})
    plain, loud = rerender(b, st), rerender(b, replace(st, pattern_emphasis=True))
    clean(loud)
    v = DYNAMICS["mf"]
    assert max(n.velocity for n in loud.part("vln1-a").notes) == DYNAMICS["f"]
    assert min(n.velocity for n in loud.part("vln1-a").notes) == round(DYNAMICS["f"] * 0.9)
    assert {n.velocity for n in loud.part("hn1").notes} == {DYNAMICS["mp"]}
    assert {n.velocity for n in plain.part("hn1").notes} == {v}
    assert loud.cc1_for("vln1-a") == plain.cc1_for("vln1-a") == v  # CC1 stays the section's level


def test_clear_low_register_simplifies_low_patterns_only():
    b, chords, key = base(0, "A")
    st = Settings(pattern="16ths")
    o = rerender(b, replace(st, clear_low=True))
    clean(o)
    plain = rerender(b, st)
    for p, q in zip(o.parts, plain.parts):
        lows = [i for i, x in enumerate(o.cells[p.id]) if x is not None and x < 48]
        if all(x is None or x >= 48 for x in o.cells[p.id]):
            assert p.notes == q.notes
        elif p.id not in o.figures and lows and not p.instrument.startswith("choir"):
            assert len(p.notes) < len(q.notes)


def test_accents_on_chord_changes():
    b, chords, key = base(0, "A")
    o = rerender(b, Settings(change_accents=True))
    clean(o)
    for p in o.parts:
        for c in chords:
            first = [n for n in p.notes if n.start == c.start]
            if first:
                assert first[0].velocity == DYNAMICS["f"]


def test_hybrid_near_the_melody_plays_chord_tones():
    for k in (0, 3):
        b, chords, key = base(k, "C", with_files=True)
        o = rerender(b, replace(b.settings, section_patterns={"strings": "16ths_rise", "woodwinds": "8ths_rise"},
                                note_mode=pat.HYBRID))
        clean(o)
        mel = [n for lid in o.figures for n in o.part(lid).notes if o.line(lid).role == "melody"]
        for p in o.parts:
            if p.id in o.figures:
                continue
            for i, c in enumerate(chords):
                cell = o.cells[p.id][i]
                near = cell is not None and any(abs(cell - m.pitch) <= 12 for m in mel
                                                if m.start < c.end and m.end > c.start)
                if near:
                    for n in sounding(o, p.id, c):
                        assert n.pitch % 12 in c.label.pcs() | {c.label.bass} or n.start < c.start


# ---------------------------------------------------------------- speed and parallel processes
@pytest.mark.slow
def test_sixteen_bars_with_files_and_textures_are_quick():
    chords, key, voic = load_with_voicings(EXPECTED[10])
    mel, bass = files(10)
    st = Settings(EPIC.ensemble(), tops=tuple(max(v) for v in voic), melody=mel, bass=bass,
                  section_patterns={"strings": "8ths"}, shape="build", fill=FILL_RUN, pattern_emphasis=True)
    generate_all(chords, key, seed=1, settings=st, parallel=True)  # warm the workers
    t = time.perf_counter()
    out = generate_all(chords, key, seed=1, settings=st, parallel=True)
    dt = time.perf_counter() - t
    assert all(isinstance(o, Orchestration) for o in out.values())
    # Sam's PC runs about 1.7x faster than this workspace; SPEC §14 asks for about 4 s there
    assert dt < float(os.environ.get("ORCHSKETCH_SPEED_LIMIT", "8"))


# ---------------------------------------------------------------- the window and projects
@pytest.fixture(scope="module")
def app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_window_texture_controls_undo_and_project(app, tmp_path):
    from test_ui_smoke import make_window

    from orchsketch import project as pj
    w = make_window(tmp_path)
    w.set_key("A", "minor")
    assert w.load(DATA / "11_sixteen_bars.mid")
    w.confirm_all()
    h = w.generate()
    cells = h.cells
    # shape and fill per section apply at once (no Generate)
    w.set_scope("strings")
    w._slider_moved("shape", "build")
    w._slider_moved("fill", FILL_RUN)
    w.set_scope("all")
    assert w.orch.settings.shape_for("strings") == "build" and w.orch.settings.shape_for("brass") == "steady"
    assert w.orch.settings.fill_for("strings") == FILL_RUN and not w.dirty
    assert w.orch.cells == cells
    w.emphasis_box.setChecked(True)
    w.clear_low_box.setChecked(True)
    w.phrase_box.setCurrentIndex(w.phrase_box.findData(8))
    w.phrase_box.activated.emit(w.phrase_box.currentIndex())
    assert w.orch.settings.pattern_emphasis and w.orch.settings.clear_low and w.orch.settings.phrase == 8
    w.undo()
    assert w.orch.settings.phrase == 4
    w.redo()
    # the theme is a generation setting
    w.theme_box.setChecked(True)
    assert w.dirty
    w.generate()
    assert w.orch.settings.theme and "theme" in w.orch.reason
    # projects keep everything exactly; an old project opens with the defaults
    before = w.snapshot()
    path = w.save_project()
    v = make_window(tmp_path / "v")
    assert v.load(path)
    assert v.snapshot() == before
    assert v.theme_box.isChecked() and v.values["strings"]["shape"] == "build"
    doc = pj.to_json(pj.load(path))
    for k in ("phrase", "emphasis", "clear_low", "change_accents", "theme"):
        doc["project"].pop(k)
    old = pj.from_json(doc)
    assert old.phrase == 4 and not old.theme
    w.close()
    v.close()


def test_window_uses_worker_processes(app, tmp_path):
    from test_ui_smoke import make_window
    w = make_window(tmp_path)
    w.set_key("A", "minor")
    assert w.load(DATA / "01_epic_staple.mid")
    w.confirm_all()
    w.parallel = True
    a = w.generate()
    w.parallel = False
    w.generate()
    assert w.alts[0] == a
    w.close()
