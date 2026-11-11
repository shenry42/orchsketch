"""SPEC §8: the 12 textbook progressions. Each chord's expected label must be the best
guess (stricter than the v1 pass rule, which also accepts it among the alternatives)."""
import json
from pathlib import Path

import pytest

from orchsketch.analysis import AnalysisSession
from orchsketch.midi_io import PPQ, read_chord_file, read_monophonic_file
from orchsketch.theory import Key

DATA = Path(__file__).parent / "data"
EXPECTED = sorted(DATA.glob("*.expected.json"))


def test_twelve_tests_present():
    assert len(EXPECTED) == 12


@pytest.mark.parametrize("exp_path", EXPECTED, ids=lambda p: p.name.split(".")[0])
def test_progression(exp_path):
    exp = json.loads(exp_path.read_text(encoding="utf-8"))
    key = Key(exp["key"]["tonic"], exp["key"]["mode"])
    clip = read_chord_file(DATA / exp["file"])
    assert clip.bars == exp["bars"]
    s = AnalysisSession(clip, key)
    got = s.chord_results
    assert len(got) == len(exp["chords"]), [r.label.symbol(key) if r.label else "?" for r in got]
    for r, e in zip(got, exp["chords"]):
        where = f"{e['label']} at beat {e['start_beat']}"
        assert r.segment.start == round(e["start_beat"] * PPQ), where
        assert r.segment.length == round(e["beats"] * PPQ), where
        assert r.recognized, where
        assert r.label.symbol(key) == e["label"], where
        assert r.label.roman(key) == e["roman"], where
        alts = [a.symbol(key) for a in r.alternatives]
        for a in e.get("also_in_alternatives", []):
            assert a in alts, f"{where}: {a} not in {alts}"
        assert r.segment.pedal == e.get("pedal", False), where
    for k in ("melody_file", "bass_file"):
        if k in exp:
            mono = read_monophonic_file(DATA / exp[k])
            assert mono.bars == exp["bars"]
