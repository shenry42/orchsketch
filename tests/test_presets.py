import json

import pytest

from orchsketch.instruments import DataError, instruments
from orchsketch.presets import Preset, builtin_presets, find, load_all, parse_preset, preset_id, save_preset


def test_builtin_presets_match_the_spec():
    names = [p.name for p in builtin_presets()]
    assert names == ["Strings only", "Strings + horns", "Brass + choir", "Full epic",
                     "Woodwinds + strings (soft)", "Low and heavy"]
    insts = instruments()
    full = find(builtin_presets(), "full_epic")
    assert set(full.instruments) == set(insts) and (full.forces, full.density, full.dynamics) == ("section", 5, "mf")
    low = find(builtin_presets(), "low_heavy")
    assert {"choir_tenor", "choir_bass", "contrabassoon", "tuba"} <= set(low.instruments)
    assert not {"choir_soprano", "choir_alto", "violins_1"} & set(low.instruments)
    soft = find(builtin_presets(), "woodwinds_strings_soft")
    assert soft.dynamics == "p" and soft.density < 5


def test_save_and_load_your_own(tmp_path):
    p = Preset(preset_id("Night Rise!"), "Night Rise!", ("cellos", "horn"), "divisi", 3, "f")
    path = save_preset(p, tmp_path)
    assert path.name == "user_night_rise.json"
    (tmp_path / "broken.json").write_text("{nope", encoding="utf-8")
    all_, problems = load_all(tmp_path)
    mine = find(all_, p.id)
    assert mine == p and not mine.builtin and len(problems) == 1 and "broken.json" in problems[0]
    assert mine.ensemble().instruments == frozenset({"cellos", "horn"})


def test_bad_presets_are_rejected():
    with pytest.raises(DataError, match="unknown instrument"):
        parse_preset({"id": "x", "name": "X", "instruments": ["kazoo"]})
    with pytest.raises(DataError, match="out of range"):
        parse_preset({"id": "x", "name": "X", "instruments": ["horn"], "density": 9})
    with pytest.raises(DataError, match="Milestone 5"):
        parse_preset({"id": "x", "name": "X", "instruments": ["horn"], "character": "moderate"})
