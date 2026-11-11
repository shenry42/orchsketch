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
