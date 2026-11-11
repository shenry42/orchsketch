from helpers import block, write_mid
from orchsketch.analysis.segment import segment_clip
from orchsketch.midi_io import BAR, PPQ, read_chord_file

CM = [48, 60, 63, 67]
AB = [44, 60, 63, 68]


def seg(tmp_path, notes, name="a.mid"):
    return segment_clip(read_chord_file(write_mid(tmp_path / name, notes)))


def test_one_chord_per_bar(tmp_path):
    s = seg(tmp_path, block([(CM, 4), (AB, 4)]))
    assert [(x.start, x.end) for x in s] == [(0, BAR), (BAR, 2 * BAR)]


def test_restrike_of_same_chord_is_one_segment(tmp_path):
    s = seg(tmp_path, block([(CM, 2), (CM, 2)]))
    assert len(s) == 1 and s[0].length == BAR


def test_change_on_an_eighth(tmp_path):
    s = seg(tmp_path, block([(CM, 2.5), (AB, 1.5)]))
    assert [x.length for x in s] == [int(2.5 * PPQ), int(1.5 * PPQ)]


def test_gap_becomes_rest(tmp_path):
    notes = block([(CM, 2)]) + [(p, 3 * PPQ, 4 * PPQ) for p in AB]
    s = seg(tmp_path, notes)
    assert [x.is_rest for x in s] == [False, True, False]


def test_slight_overlap_does_not_split(tmp_path):
    notes = [(p, 0, BAR + 40) for p in CM] + [(p, BAR - 30, 2 * BAR) for p in AB]
    s = seg(tmp_path, notes)
    assert len(s) == 2 and s[1].start == BAR


def test_pedal_detected(tmp_path):
    notes = [(36, 0, 3 * BAR)]
    t = 0
    for upper in ([60, 63, 67], [60, 63, 68], [62, 65, 70]):
        notes += [(p, t, t + BAR) for p in upper]
        t += BAR
    s = seg(tmp_path, notes)
    assert len(s) == 3 and all(x.pedal for x in s) and all(x.bass == 36 for x in s)


def test_restruck_bass_is_not_a_pedal(tmp_path):
    s = seg(tmp_path, block([([36, 60, 63, 67], 4), ([36, 60, 63, 68], 4)]))
    assert not any(x.pedal for x in s)
