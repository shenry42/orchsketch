"""SPEC §8 second benchmark: Sam's own progressions (real Ableton clip exports) in tests/data/benchmark/.

Each chord's confirmed label must be the best guess. A chord outside the v1 chord list must come out
"unrecognized"; it is then set by hand to its "correct_to" symbol, as Sam would in the app. Every
progression is then orchestrated cleanly (no checker errors, no generator_must_pass warnings) by A, B and C:
with the default preset at seed 1, as scripts\\benchmark.bat builds them, and in a wider sweep (slow)."""
import json
from pathlib import Path

import pytest

from orchsketch.analysis import AnalysisSession
from orchsketch.analysis.symbols import parse_symbol
from orchsketch.checker import chords_from_session
from orchsketch.generator import APPROACHES, Ensemble, Settings, generate
from orchsketch.instruments import instruments
from orchsketch.midi_io import PPQ, read_chord_file, read_monophonic_file
from orchsketch.presets import DEFAULT_PRESET, builtin_presets, find
from orchsketch.theory import Key
from test_generator import COMBOS, SLIDER_SAMPLE, must_fix

DATA = Path(__file__).parent / "data" / "benchmark"
EXPECTED = sorted(DATA.glob("*.expected.json"))
IDS = dict(ids=lambda p: p.name.split(".")[0])


def read(exp_path):
    return json.loads(exp_path.read_text(encoding="utf-8"))


def load(exp_path):
    """Confirmed chords, key and (melody, bass) notes, the way the app gets them."""
    exp = read(exp_path)
    key = Key(exp["key"]["tonic"], exp["key"]["mode"])
    s = AnalysisSession(read_chord_file(DATA / exp["file"]), key)
    for i, e in enumerate(exp["chords"]):
        if e.get("correct_to"):
            s.correct(i, parse_symbol(e["correct_to"]))
    assert s.confirm_all() == 0
    files = {}
    for k in ("melody", "bass"):
        if exp.get(f"{k}_file"):
            files[k] = tuple(read_monophonic_file(DATA / exp[f"{k}_file"]).notes)
    return chords_from_session(s), key, files


def preset_settings(preset, **files):
    return Settings(preset.ensemble(), dynamics=preset.dynamics, section_patterns=preset.section_patterns(),
                    instrument_patterns=preset.instrument_patterns(), **files)


def test_ten_progressions_present():
    assert [p.name.split(".")[0] for p in EXPECTED] == [f"B{n:02d}" for n in range(1, 11)]


@pytest.mark.parametrize("exp_path", EXPECTED, **IDS)
def test_labels(exp_path):
    exp = read(exp_path)
    key = Key(exp["key"]["tonic"], exp["key"]["mode"])
    clip = read_chord_file(DATA / exp["file"])
    assert clip.bars == exp["bars"]
    got = AnalysisSession(clip, key).chord_results
    assert len(got) == len(exp["chords"]), [r.label.symbol(key) if r.label else "?" for r in got]
    for r, e in zip(got, exp["chords"]):
        where = f"{e['label']} at beat {e['start_beat']}"
        assert r.segment.start == round(e["start_beat"] * PPQ), where
        assert r.segment.length == round(e["beats"] * PPQ), where
        if e["label"] == "unrecognized":
            assert not r.recognized, f"{where}: read as {r.label.symbol(key)}"
            parse_symbol(e["correct_to"])  # what Sam types in must be accepted
        else:
            assert r.recognized, where
            assert r.label.symbol(key) == e["label"], where
            assert r.label.roman(key) == e["roman"], where
        assert r.segment.pedal == e.get("pedal", False), where
    for k in ("melody_file", "bass_file"):
        if k in exp:
            assert read_monophonic_file(DATA / exp[k]).bars == exp["bars"]


@pytest.mark.parametrize("exp_path", EXPECTED, **IDS)
def test_default_preset_seed_1_is_clean(exp_path):
    """What scripts\\benchmark.bat builds: Full epic, safe, seed 1; with the melody and bass files too."""
    chords, key, files = load(exp_path)
    preset = find(builtin_presets(), DEFAULT_PRESET)
    insts = instruments()
    for kind in ({}, files) if files else ({},):
        for a in APPROACHES:
            o = generate(chords, key, seed=1, approach=a, settings=preset_settings(preset, **kind))
            assert not must_fix(o.report, frozenset(o.meta.get("fixed", set()))), (a, kind.keys(), o.report.text())
            for ln in o.lines:
                lo, hi = insts[ln.instrument].playable
                assert all(lo <= n.pitch <= hi for n in o.part(ln.id).notes), (a, ln.label)


@pytest.mark.slow  # skipped by run_tests.bat; release.bat runs it
@pytest.mark.parametrize("exp_path", EXPECTED, **IDS)
def test_sweep(exp_path):
    """Every preset, every section combination, the slider samples and moderate mode, A/B/C."""
    chords, key, files = load(exp_path)
    for p in builtin_presets():
        for a in APPROACHES:
            for kind in ({}, files) if files else ({},):
                o = generate(chords, key, seed=1, approach=a, settings=preset_settings(p, **kind))
                assert not must_fix(o.report, frozenset(o.meta.get("fixed", set()))), (p.id, a, o.report.text())
    for k, combo in enumerate(COMBOS):
        a = APPROACHES[k % 3]
        o = generate(chords, key, seed=2, approach=a, ensemble=Ensemble(combo))
        assert not must_fix(o.report), (sorted(combo), a, o.report.text())
    for k, (forces, density) in enumerate(SLIDER_SAMPLE):
        for a in APPROACHES:
            o = generate(chords, key, seed=1, approach=a, ensemble=Ensemble(forces=forces, density=density),
                         settings=Settings(character="moderate", **files))
            assert not must_fix(o.report, frozenset(o.meta.get("fixed", set()))), (forces, density, a,
                                                                                    o.report.text())
