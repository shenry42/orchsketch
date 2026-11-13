"""Milestone 7 (v1.2): the pattern engine inside the generator, the checker's parallels inside patterns, pattern
alternatives 1/2/3, and the window and project parts of it.

Ground rules (SPEC §14): with every new option at its default the output is exactly v1.1's (A, v0.4 and v1.1
pattern snapshots); generated output has 0 checker errors and 0 generator_must_pass warnings; patterns never
change a pitch at a chord change."""
import json
import os
import time
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest

import checker_examples as ex
from make_v04_snapshot import note_digest
from make_v11_pattern_snapshot import preset_settings, runs as v11_runs
from orchsketch import pattern_alts as pa
from orchsketch import patterns as pat
from orchsketch.checker import ChordSpan, Part, check
from orchsketch.export import export_parts
from orchsketch.generator import APPROACHES, Settings, generate, generate_all, rerender
from orchsketch.instruments import SECTIONS, instruments
from orchsketch.midi_io import BAR, PPQ, Note, read_monophonic_file
from orchsketch.presets import builtin_presets
from orchsketch.theory import Key
from test_generator import EXPECTED, load, must_fix

DATA = Path(__file__).parent / "data"
NEW = tuple(p for p in pat.PATTERNS if p not in pat.V1_PATTERNS)
EPIC = next(p for p in builtin_presets() if p.id == "full_epic")
SNAP = json.loads((DATA / "v11_patterns_snapshot.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def base(k: int, a: str, preset: bool = False):
    chords, key = load(EXPECTED[k])
    st = preset_settings(EPIC) if preset else None
    return generate(chords, key, seed=1, approach=a, settings=st), chords, key


# ---------------------------------------------------------------- v1.1 unchanged
def _check_snapshot(only=None):
    bad = []
    n = 0
    for rid, fn in v11_runs():
        if only and not rid.startswith(only):
            continue
        n += 1
        if note_digest(fn()) != SNAP[rid]:
            bad.append(rid)
    assert n and not bad, bad


def test_v11_patterns_unchanged_test_1():
    """v1.1's patterned notes (patterns, passing tones, presets, files) come out exactly the same."""
    _check_snapshot("01_")


@pytest.mark.slow
def test_v11_patterns_unchanged_everywhere():
    _check_snapshot()


# ---------------------------------------------------------------- the engine in the generator
def _check_render(o, b, chords, key, sp, modes):
    insts = instruments()
    assert not must_fix(o.report), o.report.text()
    assert o.cells == b.cells
    assert {i.message for i in o.report.by_check("parallels")} == {i.message for i in b.report.by_check("parallels")}
    for p in o.parts:
        sec = insts[p.instrument].section
        pt = sp.get(sec, pat.SUSTAIN)
        mode = modes.get(sec, pat.CHORD_TONES)
        for i, c in enumerate(chords):
            here = [n for n in p.notes if c.start <= n.start < c.end]
            cell = b.cells[p.id][i]
            if cell is None:
                assert not here
                continue
            first = min(here, key=lambda n: n.start)
            assert first.start == c.start and first.pitch == cell or first.start < c.start
            for n in here:
                assert n.end <= c.end or pt == pat.SUSTAIN
                assert insts[p.instrument].is_comfortable(n.pitch)
                pcs = c.label.pcs() | {c.label.bass}
                if mode == pat.CHORD_TONES or sec == "choir":
                    assert n.pitch % 12 in pcs, (p.id, i, n)
                else:
                    assert n.pitch % 12 in pat.chord_scale(pcs, key), (p.id, i, n)
                    if mode == pat.HYBRID and n.start % PPQ == 0:
                        assert n.pitch % 12 in pcs, (p.id, i, n)
            if pat.library()[pt].end_on_anchor and here and here[-1].start >= c.start:
                assert max(here, key=lambda n: n.start).pitch == cell


def _sweep(k, a):
    b, chords, key = base(k, a)
    for j, pt in enumerate(NEW):
        for m, mode in enumerate(pat.NOTE_MODES):
            sp = {sec: NEW[(j + s) % len(NEW)] for s, sec in enumerate(SECTIONS)}
            modes = {sec: pat.NOTE_MODES[(m + s) % 3] for s, sec in enumerate(SECTIONS)}
            o = rerender(b, Settings(section_patterns=sp, section_note_modes=modes))
            _check_render(o, b, chords, key, sp, modes)


@pytest.mark.parametrize("k", range(0, len(EXPECTED), 3), ids=lambda k: EXPECTED[k].name[:2])
def test_new_patterns_and_note_modes_sample(k):
    _sweep(k, APPROACHES[k % 3])


@pytest.mark.slow
@pytest.mark.parametrize("k", range(len(EXPECTED)), ids=lambda k: EXPECTED[k].name[:2])
def test_new_patterns_and_note_modes_everywhere(k):
    """Every new pattern in every section (rotated) in every note mode, for A, B and C on all 12 files."""
    for a in APPROACHES:
        _sweep(k, a)


def test_accent_groupings_everywhere_in_a():
    for k in range(len(EXPECTED)):
        b, chords, key = base(k, "A")
        for g in pat.ACCENTS[1:]:
            for pt in ("8ths", "16ths", "16ths_rise", "8ths_rise"):
                o = rerender(b, Settings(pattern=pt, accent=g, note_mode=pat.HYBRID))
                assert not must_fix(o.report), (k, g, pt)
                assert o.cells == b.cells


def test_moderate_and_files_with_new_patterns():
    for k in (0, 3, 10):
        exp = EXPECTED[k]
        d = json.loads(exp.read_text(encoding="utf-8"))
        mel = tuple(read_monophonic_file(DATA / d["melody_file"]).notes)
        bass = tuple(read_monophonic_file(DATA / d["bass_file"]).notes)
        chords, key = load(exp)
        for a in APPROACHES:
            st = preset_settings(EPIC, melody=mel, bass=bass, character="moderate",
                                 section_note_modes={"strings": pat.SCALE_STEPS, "brass": pat.HYBRID},
                                 section_accents={"strings": "3+3+2"})
            st = replace(st, section_patterns={"strings": "16ths_pendulum", "brass": "8ths_octave"})
            o = generate(chords, key, seed=1, approach=a, settings=st)
            assert not must_fix(o.report, set(o.meta["fixed"])), (k, a, o.report.text())


def test_note_modes_change_the_shape_only_off_the_chord_tones():
    b, chords, key = base(0, "A")
    o1 = rerender(b, Settings(section_patterns={"strings": "16ths_rise"}))
    o2 = rerender(b, Settings(section_patterns={"strings": "16ths_rise"}, note_mode=pat.SCALE_STEPS))
    vln1 = lambda o: [n.pitch for n in o.part("vln1-a").notes]  # noqa: E731
    assert vln1(o1) != vln1(o2)
    assert len(vln1(o1)) == len(vln1(o2))  # same rhythm
    # Safe mode with Scale steps (Sam's choice): the shapes use scale notes and nothing breaks a rule
    assert any(n.pitch % 12 not in c.label.pcs() for c in chords for n in o2.part("vln1-a").notes
               if c.start <= n.start < c.end)


# ---------------------------------------------------------------- the checker: parallels inside patterns
def test_parallels_inside_a_chord_are_warnings():
    span = ex.chords(["C"])[0]
    up = [Note(p, t, t + 240) for t, p in zip(range(0, BAR, 240), (60, 64, 67, 64, 60, 64, 67, 64))]
    fifth = [Note(n.pitch - 7, n.start, n.end) for n in up]  # the same shape a 5th below
    bass = [Note(36, 0, BAR)]
    parts = [Part("a", "violins_1", tuple(up)), Part("b", "violas", tuple(fifth)), Part("c", "cellos", tuple(bass))]
    rep = check(parts, [span], Key("C", "major"))
    found = rep.by_check("pattern_parallels")
    assert len(found) == 1 and found[0].severity == "warning" and set(found[0].parts) == {"a", "b"}
    # doubled at the octave on the same notes: one line, not parallels
    octave = [Note(n.pitch - 12, n.start, n.end) for n in up]
    rep = check([parts[0], Part("b", "violas", tuple(octave)), parts[2]], [span], Key("C", "major"))
    assert not rep.by_check("pattern_parallels")
    assert not check(parts, [span], Key("C", "major"), inside=False).by_check("pattern_parallels")


def test_v1_alternating_16ths_report_inside_parallels_but_keep_their_notes():
    """Sam's call: parallels inside v1.1's patterns are reported as warnings; the notes stay v1.1's."""
    b, chords, key = base(0, "B")
    o = rerender(b, Settings(pattern=pat.SIXTEENTHS_ALT))
    assert not must_fix(o.report)
    assert all(i.severity == "warning" for i in o.report.by_check("pattern_parallels"))


# ---------------------------------------------------------------- pattern alternatives
def test_pattern_alternatives_keep_the_harmony_and_are_seeded():
    for k in (0, 7, 10):
        for a in APPROACHES:
            h, chords, key = base(k, a, preset=True)
            assert pa.pattern_alternative(h, 1) is h
            seen = set()
            for n in (2, 3):
                o = pa.pattern_alternative(h, n)
                assert pa.pattern_number(o) == n and pa.alt_name(o) == f"{a}{n}"
                assert o.cells == h.cells and not must_fix(o.report)
                assert o.settings.part_variants and o.settings.part_variants not in seen
                seen.add(o.settings.part_variants)
                again = pa.pattern_alternative(h, n)
                assert [p.notes for p in again.parts] == [p.notes for p in o.parts]  # same seed, same result
                assert pa.describe(o)


def test_regenerate_patterns_keeps_locks_and_does_not_cycle():
    h, chords, key = base(0, "A", preset=True)
    cur = pa.pattern_alternative(h, 2)
    lock = {"tba"}
    tba = dict(cur.settings.part_variants)["tba"]
    history = [cur.settings.part_variants]
    for _ in range(8):
        cur = pa.regenerate_patterns(cur, h, lock)
        assert dict(cur.settings.part_variants)["tba"] == tba
        assert cur.settings.part_variants not in history[-8:]
        assert not must_fix(cur.report) and cur.cells == h.cells
        history.append(cur.settings.part_variants)
    with pytest.raises(ValueError):
        pa.regenerate_patterns(h, h)


def test_no_patterns_means_no_pattern_alternatives():
    h, chords, key = base(0, "A")  # Sustain everywhere
    assert pa.groups(h) == {}
    o = pa.pattern_alternative(h, 2)
    assert [p.notes for p in o.parts] == [p.notes for p in h.parts]


def test_export_names_carry_the_pattern_number(tmp_path):
    h, chords, key = base(0, "A", preset=True)
    o = pa.pattern_alternative(h, 2)
    files = export_parts(o, tmp_path, "Night Rise", 140, chords[-1].end, ["vln1-a"])
    assert [f.name for f in files] == ["Night_Rise_Vln1-a_A2.mid"]
    files = export_parts(h, tmp_path, "Night Rise", 140, chords[-1].end, ["vln1-a"])
    assert [f.name for f in files] == ["Night_Rise_Vln1-a_A.mid"]  # pattern 1: v1.1's names


def test_sixteen_bars_with_every_pattern_alternative_is_quick():
    """SPEC §14: all three alternatives for 16 bars, patterns included, in about 4 s or less on Sam's PC.
    The pattern alternatives only re-render (no voicing search)."""
    exp = EXPECTED[10]
    chords, key = load(exp)
    st = replace(preset_settings(EPIC), section_note_modes={"strings": pat.HYBRID}, accent="3+3+2")
    t = time.perf_counter()
    alts = generate_all(chords, key, seed=1, settings=st)
    t_harmony = time.perf_counter() - t
    t = time.perf_counter()
    for o in alts.values():
        for n in (2, 3):
            assert not must_fix(pa.pattern_alternative(o, n).report)
    t_patterns = time.perf_counter() - t
    assert t_patterns < max(1.5, 0.6 * t_harmony), (t_harmony, t_patterns)


# ---------------------------------------------------------------- the window and projects
pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_window_pattern_controls_alternatives_undo_and_project(app, tmp_path):
    from test_ui_smoke import make_window

    from orchsketch import project as pj
    w = make_window(tmp_path)
    w.set_key("A", "minor")
    assert w.load(DATA / "01_epic_staple.mid")
    w.confirm_all()
    h = w.generate()
    assert w.pattern_tabs.count() == 3 and w.pattern_tabs.currentIndex() == 0
    assert w.orch is h and w.reason_label.text().startswith("A · ")
    # note mode and accents per section apply at once
    w.set_scope("strings")
    w._slider_moved("pattern", "16ths_rise")
    w._slider_moved("note_mode", pat.SCALE_STEPS)
    w._slider_moved("accent", "3+3+2")
    w.set_scope("all")
    assert w.orch.settings.note_mode_for("strings") == pat.SCALE_STEPS
    assert w.orch.settings.accent_for("vln1-a", "strings") == "3+3+2"
    assert w.orch.cells == h.cells
    # pattern alternatives
    w.set_pattern_tab(1)
    o2 = w.orch
    assert pa.alt_name(o2) == "A2" and o2.cells == h.cells and o2 is not w.harmony
    assert w.reason_label.text().startswith("A2 · ") and "Patterns:" in w.reason_label.text()
    assert all(f.name.endswith("_A2.mid") for f in w.files_for_all())
    w.set_lock("vln1-a", True)
    new = w.regenerate_patterns_action()
    assert new is w.orch and new.settings.part_variants != o2.settings.part_variants
    assert dict(new.settings.part_variants)["vln1-a"] == dict(o2.settings.part_variants)["vln1-a"]
    w.undo()
    assert w.orch.settings.part_variants == o2.settings.part_variants
    w.redo()
    # a harmony edit keeps the pattern choices
    w.regenerate_unlocked()
    assert w.orch.settings.part_variants == new.settings.part_variants and pa.alt_name(w.orch) == "A2"
    # other harmony tabs have their own pattern tab
    w.set_tab(1)
    assert w.pattern_tabs.currentIndex() == 0 and pa.alt_name(w.orch) == "B"
    w.set_tab(0)
    assert w.pattern_tabs.currentIndex() == 1
    # projects keep everything exactly
    before = w.snapshot()
    path = w.save_project()
    files = {f.name: f.read_bytes() for f in w.files_for_all()}
    v = make_window(tmp_path / "v")
    assert v.load(path)
    assert v.snapshot() == before
    assert pa.alt_name(v.orch) == "A2" and v.values["strings"]["note_mode"] == pat.SCALE_STEPS
    assert {f.name: f.read_bytes() for f in v.files_for_all()} == files
    # an old (v1.1) project without pattern alternatives still opens
    doc = pj.to_json(pj.load(path))
    for k in ("palts", "ptabs"):
        doc["project"].pop(k)
    old = pj.from_json(doc)
    assert old.ptabs == (0, 0, 0) and old.palts == ((None, None, None),) * 3
    w.close()
    v.close()
