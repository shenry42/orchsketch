import mido
import pytest

from helpers import block, write_mid
from orchsketch.midi_io import BAR, PPQ, InputError, Note, read_chord_file, read_monophonic_file, write_notes

AM = [45, 57, 60, 64]
F = [41, 57, 60, 65]


def test_reads_and_scales_ppq(tmp_path):
    p = write_mid(tmp_path / "a.mid", block([(AM, 4), (F, 4)], ppq=96), ppq=96)
    clip = read_chord_file(p)
    assert clip.source_ppq == 96 and clip.bars == 2 and clip.length == 2 * BAR
    assert {n.start for n in clip.notes} == {0, BAR}
    assert all(n.length == BAR for n in clip.notes)


def test_tolerance_snaps_late_start_and_early_release(tmp_path):
    notes = [(45, 0, 1900), (57, 50, 1920), (60, 0, 1870), (64, 0, 1920),
             (41, 1920 + 40, 3840), (57, 1920 - 30, 3840), (60, 1920, 3800), (65, 1920, 3840)]
    clip = read_chord_file(write_mid(tmp_path / "h.mid", notes))
    assert sorted({n.start for n in clip.notes}) == [0, BAR]
    assert all(n.end in (BAR, 2 * BAR) for n in clip.notes)


def test_off_grid_start_rejected(tmp_path):
    p = write_mid(tmp_path / "x.mid", [(60, 120, 960)])  # a 16th after the beat
    with pytest.raises(InputError, match="8th-note grid"):
        read_chord_file(p)


def test_three_four_rejected(tmp_path):
    p = write_mid(tmp_path / "x.mid", block([(AM, 3)]), timesig=(3, 4))
    with pytest.raises(InputError, match="Only 4/4"):
        read_chord_file(p)


def test_seventeen_bars_rejected_sixteen_ok(tmp_path):
    ok = write_mid(tmp_path / "ok.mid", block([(AM, 4)] * 16))
    assert read_chord_file(ok).bars == 16
    bad = write_mid(tmp_path / "bad.mid", block([(AM, 4)] * 17))
    with pytest.raises(InputError, match="17 bars"):
        read_chord_file(bad)


def test_empty_and_garbage(tmp_path):
    with pytest.raises(InputError, match="no notes"):
        read_chord_file(write_mid(tmp_path / "e.mid", []))
    junk = tmp_path / "j.mid"
    junk.write_bytes(b"not midi at all")
    with pytest.raises(InputError):
        read_chord_file(junk)
    with pytest.raises(InputError, match="not found"):
        read_chord_file(tmp_path / "missing.mid")


def test_type2_rejected(tmp_path):
    mid = mido.MidiFile(type=2)
    mid.tracks.append(mido.MidiTrack([mido.Message("note_on", note=60, time=0),
                                      mido.Message("note_off", note=60, time=480)]))
    mid.save(str(tmp_path / "t2.mid"))
    with pytest.raises(InputError, match="type 2"):
        read_chord_file(tmp_path / "t2.mid")


def test_clip_length_rounds_up_to_whole_bars(tmp_path):
    clip = read_chord_file(write_mid(tmp_path / "a.mid", block([(AM, 6)])))
    assert clip.bars == 2


def test_monophonic_rules(tmp_path):
    legato = [(60, 0, 500), (62, 480, 960)]
    clip = read_monophonic_file(write_mid(tmp_path / "m.mid", legato))
    assert clip.notes[0].end == 480
    chordy = [(60, 0, 480), (64, 10, 480)]
    with pytest.raises(InputError, match="one note at a time"):
        read_monophonic_file(write_mid(tmp_path / "c.mid", chordy), "Bass")


def test_write_starts_at_bar_one_with_tempo_and_timesig(tmp_path):
    notes = [Note(57, 0, BAR, 90), Note(60, 0, BAR, 90), Note(41, BAR, 2 * BAR, 80)]
    p = write_notes(tmp_path / "out.mid", notes, tempo_bpm=140, track_name="Chords", length=2 * BAR)
    mid = mido.MidiFile(str(p))
    assert mid.ticks_per_beat == PPQ and mid.type == 0
    msgs = list(mid.tracks[0])
    tempo = next(m for m in msgs if m.type == "set_tempo")
    assert round(mido.tempo2bpm(tempo.tempo)) == 140
    ts = next(m for m in msgs if m.type == "time_signature")
    assert (ts.numerator, ts.denominator) == (4, 4)
    first_on = 0
    for m in msgs:
        first_on += m.time
        if m.type == "note_on":
            break
    assert first_on == 0  # no lead-in: lines up when dropped at a bar line
    assert sum(m.time for m in msgs) == 2 * BAR


def test_round_trip_is_exact(tmp_path):
    src = read_chord_file(write_mid(tmp_path / "a.mid", block([(AM, 2), (F, 2), (AM, 4)])))
    out = write_notes(tmp_path / "b.mid", src.notes, 140, length=src.length)
    again = read_chord_file(out)
    assert again.notes == src.notes and again.length == src.length
