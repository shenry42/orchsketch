"""Milestone 9 (v1.4): expression — CC curves, swells, tremolo part, risers, velocity shaping, balance, humanize,
long notes only in a high doubling. With every new option at its default, everything is v1.3's."""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
from dataclasses import replace
from pathlib import Path

import mido
import pytest

from orchsketch import expression as ex
from orchsketch import patterns as pat
from orchsketch.export import BOTH, export_all, export_part_files
from orchsketch.generator import DOUBLE_ID, Settings, generate, generate_all, rerender
from orchsketch.instruments import instruments
from orchsketch.midi_io import BAR, PPQ, Note
from test_generator import EXPECTED, load_with_voicings, must_fix
from test_textures import EPIC, base, clean, files

HERE = Path(__file__).parent
SNAP = HERE / "data" / "v13_export_snapshot.json"
EXPRESSION_ON = dict(curves=True, swell="chord", phrase_arcs=True, beat_accents=True, balance=True,
                     humanize="medium", riser=2, shepard=True, long_doubling=True)


def epic(k, a, with_files=False, **kw):
    chords, key, voic = load_with_voicings(EXPECTED[k])
    mel, bass = files(k) if with_files else (None, None)
    pats = dict(EPIC.patterns)
    secs = ("strings", "brass", "woodwinds", "choir")
    st = Settings(EPIC.ensemble(), tops=tuple(max(v) for v in voic), melody=mel, bass=bass,
                  section_patterns=tuple((s, p) for s, p in pats.items() if s in secs),
                  instrument_patterns=tuple((s, p) for s, p in pats.items() if s not in secs), **kw)
    return generate(chords, key, seed=1, approach=a, settings=st), chords


def length_of(chords):
    return max(c.end for c in chords)


# ---------------------------------------------------------------- defaults: v1.3 exactly
def test_defaults_export_exactly_v13():
    """The exported files (parts, full score, combined divisi) of v1.3, byte for byte."""
    import sys
    sys.path.insert(0, str(HERE))
    from make_v13_export_snapshot import export_hashes, snapshot_runs
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    runs = snapshot_runs()
    assert len(runs) == len(snap)
    for name, orch, length in runs:
        assert "expression" not in orch.meta
        assert export_hashes(orch, length) == snap[name], name


def test_new_settings_are_render_only_and_default_off():
    from orchsketch.generator import RENDER_ONLY
    st = Settings()
    for f in ("curves", "swell", "section_swells", "phrase_arcs", "beat_accents", "balance", "humanize", "riser",
              "riser_section", "shepard", "long_doubling"):
        assert f in RENDER_ONLY
    assert not st.curves_on() and st.humanize == "off" and st.riser == 0 and not st.balance
    with pytest.raises(ValueError):
        Settings(swell="loud")
    with pytest.raises(ValueError):
        Settings(riser=3)
    with pytest.raises(ValueError):
        Settings(humanize="heavy")


# ---------------------------------------------------------------- CC curves
def _cc(points, cc):
    return [(t, v) for t, c, v in points if c == cc]


def test_curves_follow_the_shape_and_export_instead_of_the_constant_cc1(tmp_path):
    b, chords, key = base(10, "B")
    o = rerender(b, replace(b.settings, shape="build", curves=True))
    clean(o)
    assert [p.notes for p in o.parts] == [p.notes for p in rerender(b, replace(b.settings, shape="build")).parts]
    curves = o.meta["expression"]["curves"]
    assert set(curves) == {ln.id for ln in o.sounding_lines}
    vln = curves["vln1-a"] if "vln1-a" in curves else next(v for k, v in curves.items() if k.startswith("vln"))
    first = ex.cc_at(vln, 1, 0, 0)
    last = ex.cc_at(vln, 1, length_of(chords) - PPQ, 0)
    assert first < last  # Build rises to the peak (your settings)
    lid = next(k for k in curves)
    f = export_part_files(o, lid, tmp_path, "T", 140, length_of(chords))[0]
    msgs = [m for m in mido.MidiFile(f).tracks[0] if m.type == "control_change"]
    assert {m.control for m in msgs} == {1, 11}
    assert len([m for m in msgs if m.control == 1]) > 2  # a curve, not one value


def test_winds_and_brass_arc_on_cc11_strings_on_cc1():
    b, chords, key = base(0, "B")
    o = rerender(b, replace(b.settings, curves=True))
    insts = instruments()
    for lid, pts in o.meta["expression"]["curves"].items():
        sec = insts[o.line(lid).instrument].section
        e = [v for _, v in _cc(pts, 11)]
        if sec in ("woodwinds", "brass"):
            assert min(e) <= ex.CC11_LOW + 2 and max(e) == 127
        else:
            assert e == [127]
            d = [v for _, v in _cc(pts, 1)]
            assert max(d) - min(d) >= 6  # the phrase arc (and the swells in held chords)


def test_swells_rise_into_the_chord_change_and_turn_curves_on():
    b, chords, key = base(0, "B")
    o = rerender(b, replace(b.settings, swell="chord"))
    pts = o.meta["expression"]["curves"]
    lid = next(iter(pts))
    z = chords[1].start
    assert ex.cc_at(pts[lid], 1, z - ex.SIXTEENTH, 0) > ex.cc_at(pts[lid], 1, z - PPQ, 0) + 10
    assert ex.cc_at(pts[lid], 1, z, 0) < ex.cc_at(pts[lid], 1, z - ex.SIXTEENTH, 0)
    down = rerender(b, replace(b.settings, swell="downbeat")).meta["expression"]["curves"][lid]
    assert ex.cc_at(down, 1, z - ex.SIXTEENTH, 0) < ex.cc_at(pts[lid], 1, z - ex.SIXTEENTH, 0)
    # per section: only the brass swells
    o2 = rerender(b, replace(b.settings, section_swells=(("brass", "chord"),)))
    insts = instruments()
    for k, pts2 in o2.meta["expression"]["curves"].items():
        jump = ex.cc_at(pts2, 1, z - ex.SIXTEENTH, 0) - ex.cc_at(pts2, 1, z - PPQ, 0)
        assert (jump > 10) == (insts[o2.line(k).instrument].section == "brass"), k


def test_curve_helper_ramps():
    vals = [30, 50, 65, 80]
    pts = ex.curve(vals, "strings", [], [], 4 * BAR, 4)
    assert ex.cc_at(pts, 1, 0, 0) < ex.cc_at(pts, 1, 3 * BAR + PPQ, 0)
    # a rise that keeps rising ramps over the whole bar; a single drop is instant
    pts = ex.curve([80, 50, 50, 50], "woodwinds", [], [], 4 * BAR, 4)
    assert ex.cc_at(pts, 1, BAR - ex.SIXTEENTH, 0) == 80 and ex.cc_at(pts, 1, BAR, 0) == 50


def test_audition_expression_is_relative():
    pts = [[0, 1, 120], [0, 11, 127], [BAR, 1, 30]]
    out = ex.audition_expression(pts)
    assert out[0] == (0, 127) and 60 <= out[-1][1] <= 70


# ---------------------------------------------------------------- velocity shaping, balance
def test_phrase_arcs_and_beat_accents_change_velocities_only():
    b, chords, key = base(0, "B")
    o = rerender(b, replace(b.settings, phrase_arcs=True, beat_accents=True))
    clean(o)
    for p, q in zip(b.parts, o.parts):
        assert [(n.pitch, n.start, n.end) for n in p.notes] == [(n.pitch, n.start, n.end) for n in q.notes]
    assert any(n.velocity != m.velocity for p, q in zip(b.parts, o.parts) for n, m in zip(p.notes, q.notes))
    o2 = rerender(b, replace(b.settings, beat_accents=True))
    beat1 = [n.velocity for p in o2.parts for n in p.notes if n.start % BAR == 0]
    assert beat1 and all(v > 80 for v in beat1)


def test_balance_puts_woodwinds_a_step_under():
    b, chords, key = base(0, "B")
    o = rerender(b, replace(b.settings, balance=True))
    insts = instruments()
    for p in o.parts:
        sec = insts[p.instrument].section
        for n in p.notes:
            assert n.velocity == (65 if sec == "woodwinds" else 80) or p.id in o.figures
        if p.notes:
            assert o.cc1_for(p.id) == (65 if sec == "woodwinds" else 80)


# ---------------------------------------------------------------- tremolo
def test_tremolo_exports_as_its_own_part(tmp_path):
    b, chords, key = base(0, "B")
    o = rerender(b, replace(b.settings, section_patterns=(("strings", "tremolo"), ("brass", "tremolo"))))
    clean(o)
    trem = o.meta["expression"]["trem"]
    insts = instruments()
    assert trem and all(insts[o.line(k).instrument].section == "strings" for k in trem)
    sus = rerender(b, replace(b.settings, section_patterns=()))
    for p in o.parts:  # same pitches and starts as Sustain (re-struck at every chord)
        assert {n.pitch for n in p.notes} == {n.pitch for n in sus.part(p.id).notes}
    files = export_all(o, tmp_path, "T", 140, length_of(chords))
    names = {f.name for f in files}
    lid = next(iter(trem))
    code = o.line(lid).export
    assert f"T_{code}-trem_B.mid" in names
    assert f"T_{code}_B.mid" not in names  # every note is tremolo
    full = mido.MidiFile(next(f for f in files if "_Full_" in f.name))
    assert any(t.name.endswith(" trem") for t in full.tracks)


def test_tremolo_is_a_strings_only_pattern_and_never_for_the_choir():
    assert pat.library()[ex.TREMOLO].kind == "sustain"
    assert not pat.allowed(ex.TREMOLO, True)
    assert pat.PATTERNS[:6] == pat.V1_PATTERNS


# ---------------------------------------------------------------- risers
def test_riser_climbs_into_the_hit_and_lands_on_the_chord_tone():
    o, chords = epic(10, "B", True, shape="build_hit", riser=2)
    clean(o)
    rise = o.meta["expression"]["rise"]
    assert rise
    for lid, (a, z, layer, layers) in rise.items():
        assert z - a == 2 * BAR and z == 15 * BAR and layers == 1
        notes = [n for n in o.part(lid).notes if a <= n.start < z]
        ps = [n.pitch for n in notes]
        assert ps == sorted(ps) and ps[-1] < ps[0] + 13
        land = next(n for n in o.part(lid).notes if n.start == z)
        assert land.pitch > ps[-1]
        assert notes[-1].velocity > notes[0].velocity
        assert (a, z) in o.part(lid).free


def test_shepard_riser_layers_crossfade(tmp_path):
    o, chords = epic(0, "B", riser=1, shepard=True)
    clean(o)
    rise = o.meta["expression"]["rise"]
    assert len(rise) == 3 and sorted(v[2] for v in rise.values()) == [0, 1, 2]
    curves = o.meta["expression"]["curves"]
    top = next(k for k, v in rise.items() if v[2] == 0)
    bottom = next(k for k, v in rise.items() if v[2] == 2)
    a, z = rise[top][:2]
    assert ex.cc_at(curves[top], 11, z - ex.SIXTEENTH, 0) < ex.cc_at(curves[top], 11, a, 0)
    assert ex.cc_at(curves[bottom], 11, z - ex.SIXTEENTH, 0) > ex.cc_at(curves[bottom], 11, a, 0)
    names = {f.name for f in export_all(o, tmp_path, "T", 140, length_of(chords))}
    assert sum("-rise_" in n for n in names) == 3


def test_riser_too_long_for_the_clip_shortens():
    o, chords = epic(0, "B", riser=4)
    rise = o.meta["expression"].get("rise") or {}
    assert all(z - a <= chords[-1].start for a, z, _, _ in rise.values())


# ---------------------------------------------------------------- long notes only in a high doubling
def test_high_doubling_keeps_only_long_notes():
    o, chords = epic(0, "B", True)
    if DOUBLE_ID not in {p.id for p in o.parts if p.notes}:
        pytest.skip("no melody doubling in this setup")
    o2 = rerender(o, replace(o.settings, long_doubling=True))
    clean(o2)
    before = o.part(DOUBLE_ID).notes
    after = o2.part(DOUBLE_ID).notes
    assert all(n.end - n.start >= PPQ or n.pitch < 84 for n in after)
    assert len(after) <= len(before)
    for p in o.parts:
        if p.id != DOUBLE_ID:
            assert p.notes == o2.part(p.id).notes


# ---------------------------------------------------------------- humanize
def test_humanize_is_seeded_and_only_in_export(tmp_path):
    b, chords, key = base(0, "B")
    o = rerender(b, replace(b.settings, humanize="medium"))
    assert [p.notes for p in o.parts] == [p.notes for p in b.parts]  # the grid stays on the grid
    a1 = export_all(o, tmp_path / "1", "T", 140, length_of(chords))
    a2 = export_all(o, tmp_path / "2", "T", 140, length_of(chords))
    assert [f.read_bytes() for f in a1] == [f.read_bytes() for f in a2]
    plain = export_all(b, tmp_path / "3", "T", 140, length_of(chords))
    assert [f.read_bytes() for f in a1] != [f.read_bytes() for f in plain]


def test_humanize_helper_keeps_notes_sane():
    notes = [Note(60, 0, 240), Note(60, 240, 480), Note(64, 0, 960), Note(67, 480, 600)]
    out = ex.humanize(notes, "k", "medium")
    assert ex.humanize(notes, "k", "medium") == out
    assert all(n.start >= 0 and n.end > n.start for n in out)
    c = sorted((n for n in out if n.pitch == 60), key=lambda n: n.start)
    assert c[0].end <= c[1].start
    assert all(abs(n.start - m.start) <= 12 for n, m in zip(sorted(notes, key=lambda n: (n.start, n.pitch)),
                                                         sorted(out, key=lambda n: (n.start, n.pitch))))


# ---------------------------------------------------------------- everything at once
@pytest.mark.parametrize("k", [0, 3, 10])
def test_everything_on_sample(k):
    for a in ("A", "B", "C"):
        o, chords = epic(k, a, k in (0, 3, 10), shape="build_hit", **EXPRESSION_ON)
        clean(o)
        assert not must_fix(o.report, set(o.meta.get("fixed", ())))
        with tempfile.TemporaryDirectory() as d:
            export_all(o, Path(d), "T", 140, length_of(chords), BOTH, combined=True)


@pytest.mark.parametrize("k", range(len(EXPECTED)))
def test_every_expression_option_everywhere(k):
    """All 12 files x A/B/C x a few expression setups: 0 errors, 0 must-pass warnings, the harmony unchanged."""
    setups = [dict(EXPRESSION_ON), dict(EXPRESSION_ON, shepard=False, riser=1, riser_section="woodwinds"),
              dict(curves=True, swell="downbeat", shape="breakdown", section_patterns=(("strings", "tremolo"),)),
              dict(riser=4, shape="build_hit", section_patterns=(("strings", "arp_wave"),), balance=True),
              dict(shape="pulse_bed", balance=True, swell="chord",
                   section_patterns=(("strings", "arp_wave16"), ("woodwinds", "8ths")))]
    for a in ("A", "B", "C"):
        plain, chords = epic(k, a)
        for kw in setups:
            o = rerender(plain, replace(plain.settings, **kw))
            assert o.cells == plain.cells
            clean(o)


def test_expression_keeps_generation_quick():
    """16 bars with files, every expression option on: no slower than without (render only, a small margin)."""
    chords, key, voic = load_with_voicings(EXPECTED[10])
    mel, bass = files(10)
    st0 = Settings(EPIC.ensemble(), tops=tuple(max(v) for v in voic), melody=mel, bass=bass,
                   section_patterns=(("strings", "8ths"),))
    o = generate(chords, key, seed=1, approach="B", settings=st0)
    t = time.perf_counter()
    rerender(o, st0)
    t0 = time.perf_counter() - t
    t = time.perf_counter()
    rerender(o, replace(st0, shape="build_hit", **EXPRESSION_ON))
    t1 = time.perf_counter() - t
    assert t1 < t0 + 1.0, (t0, t1)


# ---------------------------------------------------------------- playback
def test_player_sends_expression_and_mutes_tremolo_with_its_part():
    from orchsketch.playback.player import Sequence

    class Be:
        def __init__(self):
            self.log = []

        def program(self, ch, prog):
            self.log.append(("prog", ch, prog))

        def noteon(self, ch, p, v):
            self.log.append(("on", ch, p))

        def noteoff(self, ch, p):
            self.log.append(("off", ch, p))

        def cc(self, ch, c, v):
            self.log.append(("cc", ch, c, v))

    be = Be()
    seq = Sequence(be, [("a", 48, [Note(60, 0, 480)]), ("a/trem", 44, [Note(64, 0, 480)])], 960,
                   {"a": "strings"}, {"a": [(0, 127), (240, 90)]})
    seq.set_mute("a", True)
    seq.advance_to(960)
    assert not [x for x in be.log if x[0] == "on"]
    assert ("cc", seq.part_channel["a"], 11, 90) in be.log


# ---------------------------------------------------------------- the window, undo and projects
def test_window_expression_controls_undo_project_and_playback(tmp_path):
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from test_ui_smoke import make_window

    from orchsketch import project as pj
    w = make_window(tmp_path)
    w.set_key("A", "minor")
    assert w.load(HERE / "data" / "01_epic_staple.mid")
    w.confirm_all()
    from orchsketch.ui.main_window import EXPRESSION_DEFAULTS
    assert dict(w.snapshot().expression) == EXPRESSION_DEFAULTS  # a new project: balance + long doubling on
    w.balance_box.setChecked(False)
    w.long_dbl_box.setChecked(False)
    h = w.generate()
    assert "expression" not in h.meta and not h.settings.balance
    w.curves_box.setChecked(True)
    assert w.orch.settings.curves and w.orch.meta["expression"]["curves"] and w.orch.cells == h.cells
    w.set_scope("brass")
    w._slider_moved("swell", "chord")
    w.set_scope("all")
    assert w.orch.settings.swell_for("brass") == "chord" and w.orch.settings.swell_for("strings") == "off"
    w.humanize_box.setCurrentIndex(w.humanize_box.findData("light"))
    w.humanize_box.activated.emit(w.humanize_box.currentIndex())
    w.riser_box.setCurrentIndex(w.riser_box.findData(1))
    w.riser_box.activated.emit(w.riser_box.currentIndex())
    w.shepard_box.setChecked(True)
    assert w.orch.settings.humanize == "light" and w.orch.settings.riser == 1 and w.orch.settings.shepard
    assert "riser" in w.reason_label.text().lower()
    names = {f.name for f in w.files_for_all()}
    assert any("-rise_" in n for n in names)
    lid = next(iter(w.orch.meta["expression"]["rise"]))
    assert any("-rise_" in f.name for f in w.files_for_part(lid))
    assert w.play()  # the audition takes the curves (fake backend in tests)
    w.stop()
    before = w.snapshot()
    w.undo()
    assert not w.orch.settings.shepard
    w.redo()
    assert w.snapshot() == before
    path = w.save_project()
    files = {f.name: f.read_bytes() for f in w.files_for_all()}
    v = make_window(tmp_path / "v")
    assert v.load(path)
    assert v.snapshot() == before
    assert v.orch.meta["expression"] == w.orch.meta["expression"]
    assert {f.name: f.read_bytes() for f in v.files_for_all()} == files
    # a v1.3 project (no expression field) opens with everything off
    doc = pj.to_json(pj.load(path))
    doc["project"].pop("expression")
    old = pj.from_json(doc)
    assert old.expression == ()
    pj.save(old, tmp_path / "old.osk")
    u = make_window(tmp_path / "u")
    assert u.load(tmp_path / "old.osk")
    assert not u.balance_box.isChecked() and not u.long_dbl_box.isChecked() and not u.orch.settings.balance
    u.close()
    w.close()
    v.close()


# ---------------------------------------------------------------- v1.4 tuning after the first ear test
def test_breakdown_fades_the_leaving_sections_first():
    """X2: woodwinds and choir step down in the bar before Breakdown takes them out (and ramp down on CC1)."""
    b, chords, key = base(10, "B")
    o = rerender(b, replace(b.settings, shape="breakdown", curves=True))
    clean(o)
    insts = instruments()
    wood = [p for p in o.parts if insts[p.instrument].section == "woodwinds" and p.notes]
    assert wood
    last_in = max(n.start for p in wood for n in p.notes if n.start < 8 * BAR) // BAR  # their last bar before the break
    for p in wood:
        before = [n.velocity for n in p.notes if n.start // BAR == last_in - 1]
        fading = [n.velocity for n in p.notes if n.start // BAR == last_in]
        if before and fading:
            assert max(fading) < min(before)
        pts = o.meta["expression"]["curves"][p.id]
        assert ex.cc_at(pts, 1, (last_in + 1) * BAR - ex.SIXTEENTH, 0) < ex.cc_at(pts, 1, last_in * BAR, 0) - 10


def test_own_pattern_stands_out_with_emphasis():
    """X7: a part given its own pattern (the cello wave) a step over the section's pattern under emphasis."""
    b, chords, key = base(0, "B")
    st = replace(b.settings, section_patterns=(("strings", "8ths"),), pattern_emphasis=True)
    plain = rerender(b, st)
    vc = next(p.id for p in plain.parts if p.id.startswith("vc") and p.notes)
    own = rerender(b, replace(st, part_patterns=((vc, "arp_wave"),)))
    assert max(n.velocity for n in own.part(vc).notes) > max(n.velocity for n in plain.part(vc).notes)


def test_audition_sets_channel_volume():
    from orchsketch.playback.player import Sequence

    class Be:
        def __init__(self):
            self.log = []

        def program(self, ch, prog):
            pass

        def noteon(self, ch, p, v):
            pass

        def noteoff(self, ch, p):
            pass

        def cc(self, ch, c, v):
            self.log.append((ch, c, v))

    be = Be()
    seq = Sequence(be, [("a", 48, [Note(60, 0, 480)]), ("a/trem", ex.TREMOLO_PROGRAM, [Note(64, 0, 480)])], 960)
    assert (seq.channels[ex.TREMOLO_PROGRAM], 7, 127) in be.log and (seq.channels[48], 7, 100) in be.log
