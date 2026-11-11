from helpers import block, write_mid
from orchsketch.analysis import AnalysisSession, parse_symbol
from orchsketch.midi_io import read_chord_file
from orchsketch.theory import Key


def make(tmp_path):
    clip = read_chord_file(write_mid(tmp_path / "a.mid", block([([45, 57, 60, 64], 4), ([48, 49, 50, 51], 4)])))
    return AnalysisSession(clip, Key("A", "minor"))


def test_statuses_and_correction(tmp_path):
    s = make(tmp_path)
    good, odd = s.results
    assert good.status == "auto" and good.label.symbol(s.key) == "Am"
    assert odd.label is None  # unrecognized
    assert s.confirm_all() == 1 and not s.all_confirmed
    s.correct(1, parse_symbol("Cm"))
    assert odd.status == "corrected" and s.all_confirmed
    assert s.confirmed_label(1) == parse_symbol("Cm")
    assert s.corrections_dict() == {"1": {"root": 0, "quality": "min", "bass": 0}}


def test_generation_only_sees_confirmed(tmp_path):
    s = make(tmp_path)
    assert s.confirmed_label(0) is None
    s.confirm(0)
    assert s.confirmed_label(0).symbol(s.key) == "Am"


def test_choosing_the_best_guess_is_a_confirmation(tmp_path):
    s = make(tmp_path)
    s.correct(0, parse_symbol("Am"))
    assert s.results[0].status == "confirmed"


def test_key_change_keeps_corrections(tmp_path):
    s = make(tmp_path)
    s.correct(1, parse_symbol("Cm"))
    s.confirm(0)
    s.set_key(Key("C", "major"))
    assert s.results[1].correction == parse_symbol("Cm")
    assert s.results[0].status == "auto"
    assert s.results[0].label.roman(s.key) == "vi"
