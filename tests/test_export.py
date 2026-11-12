"""Milestone 3 per-part export: names, timing, pitch, tempo, CC1, one file per divisi line."""
import mido

import checker_examples as ex
from orchsketch.export import export_parts, part_filename, safe_name
from orchsketch.generator import generate
from orchsketch.midi_io import BAR, PPQ, read_monophonic_file
from orchsketch.theory import Key


def orch():
    chords = ex.chords(["Am", "F", "C", "G"])
    return generate(chords, Key("A", "minor"), seed=1), chords


def test_names():
    assert safe_name("Night Rise!") == "Night_Rise"
    assert safe_name("  ") == "OrchSketch"
    assert part_filename("NightRise", "Vln1-a", "A") == "NightRise_Vln1-a_A.mid"


def test_every_part_round_trips(tmp_path):
    o, chords = orch()
    files = export_parts(o, tmp_path, "Test 1", 128, 4 * BAR)
    names = {f.name for f in files}
    assert "Test_1_Vln1-a_A.mid" in names and "Test_1_Vln1-b_A.mid" in names and "Test_1_Cb_A.mid" in names
    by_export = {ln.export: ln for ln in o.lines}
    for f in files:
        mid = mido.MidiFile(f)
        assert mid.type == 0 and mid.ticks_per_beat == PPQ
        msgs = list(mid.tracks[0])
        tempo = next(m for m in msgs if m.type == "set_tempo")
        assert round(mido.tempo2bpm(tempo.tempo)) == 128
        ts = next(m for m in msgs if m.type == "time_signature")
        assert (ts.numerator, ts.denominator) == (4, 4)
        cc = [m for m in msgs if m.type == "control_change"]
        assert [(m.control, m.value) for m in cc] == [(1, 80)]
        line = by_export[f.name[len("Test_1_"):-len("_A.mid")]]
        assert next(m for m in msgs if m.type == "track_name").name == line.label
        got = read_monophonic_file(f).notes if len(o.part(line.id).notes) else []
        want = list(o.part(line.id).notes)
        assert [(n.pitch, n.start, n.end, n.velocity) for n in got] == [(n.pitch, n.start, n.end, n.velocity) for n in want]
        assert sum(m.time for m in msgs) == 4 * BAR  # whole clip length, lines up in Ableton


def test_parts_that_rest_throughout_are_skipped(tmp_path):
    o, _ = orch()
    files = export_parts(o, tmp_path, "x", 120, 4 * BAR)
    exported = {f.name.split("_")[1] for f in files}
    for ln in o.lines:
        assert (ln.export in exported) == bool(o.part(ln.id).notes)


def test_export_selected_parts_only(tmp_path):
    o, _ = orch()
    files = export_parts(o, tmp_path, "x", 120, 4 * BAR, line_ids=["vc", "hn1"])
    assert sorted(f.name for f in files) == ["x_Hn1_A.mid", "x_Vc_A.mid"]


# ---------------------------------------------------------------- Milestone 6: full score and combined divisi
def _notes(track):
    out, now, on = [], 0, {}
    for m in track:
        now += m.time
        if m.type == "note_on" and m.velocity:
            on[m.note] = (now, m.velocity)
        elif m.type in ("note_off", "note_on"):
            s, v = on.pop(m.note)
            out.append((m.note, s, now, v))
    return sorted(out)


def test_full_score_is_type_1_with_one_named_track_per_part(tmp_path):
    from orchsketch.export import export_full, full_filename
    o, _ = orch()
    path = export_full(o, tmp_path, "Night Rise", 132, 4 * BAR)
    assert path.name == full_filename("Night Rise", "A") == "Night_Rise_Full_A.mid"
    mid = mido.MidiFile(path)
    assert mid.type == 1 and mid.ticks_per_beat == PPQ
    head = list(mid.tracks[0])
    assert round(mido.tempo2bpm(next(m for m in head if m.type == "set_tempo").tempo)) == 132
    ts = next(m for m in head if m.type == "time_signature")
    assert (ts.numerator, ts.denominator) == (4, 4)
    sounding = [ln for ln in o.lines if o.part(ln.id).notes]
    assert [t.name for t in mid.tracks[1:]] == [ln.label for ln in sounding]
    for tr, ln in zip(mid.tracks[1:], sounding):
        cc = [(m.control, m.value) for m in tr if m.type == "control_change"]
        assert cc == [(1, o.cc1_for(ln.id))]
        assert _notes(tr) == sorted((n.pitch, n.start, n.end, n.velocity) for n in o.part(ln.id).notes)
    assert all(sum(m.time for m in t) == 4 * BAR for t in mid.tracks)  # every track ends at the clip's end
    assert min(n.start for p in o.parts for n in p.notes) == 0  # bar 1, no lead-in


def test_combined_divisi_files_merge_unisons(tmp_path):
    from orchsketch.export import combined_groups, export_combined, merge_unisons
    from orchsketch.midi_io import Note
    o, _ = orch()
    groups = combined_groups(o)
    assert groups["Vln1-all"] == ["vln1-a", "vln1-b"] and groups["Hn-all"] == ["hn1", "hn2", "hn3", "hn4"]
    files = export_combined(o, tmp_path, "x", 120, 4 * BAR)
    assert {f.name for f in files} == {f"x_{code}_A.mid" for code in groups}
    hn = mido.MidiFile(tmp_path / "x_Hn-all_A.mid")
    got = _notes(hn.tracks[0])
    want = merge_unisons(n for lid in groups["Hn-all"] for n in o.part(lid).notes)
    assert got == sorted((n.pitch, n.start, n.end, n.velocity) for n in want)
    # same-pitch notes in two lines never overlap on one track
    merged = merge_unisons([Note(60, 0, 480, 80), Note(60, 240, 960, 100), Note(60, 960, 1200, 70), Note(64, 0, 480)])
    assert merged == [Note(64, 0, 480, 100), Note(60, 0, 960, 100), Note(60, 960, 1200, 70)]


def test_export_choices(tmp_path):
    import pytest
    from orchsketch.export import BOTH, FULL, PARTS, export_all
    o, _ = orch()
    n_parts = sum(1 for p in o.parts if p.notes)
    assert len(export_all(o, tmp_path / "p", "x", 120, 4 * BAR, PARTS)) == n_parts
    assert [f.name for f in export_all(o, tmp_path / "f", "x", 120, 4 * BAR, FULL)] == ["x_Full_A.mid"]
    both = export_all(o, tmp_path / "b", "x", 120, 4 * BAR, BOTH, combined=True)
    assert len(both) == n_parts + 1 + 8 and both[-1].name == "x_Full_A.mid"
    with pytest.raises(ValueError):
        export_all(o, tmp_path, "x", 120, 4 * BAR, "zip")
