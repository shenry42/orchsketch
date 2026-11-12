"""Milestone 6: projects (.osk). Everything reopens exactly as saved - notes, input files, corrections, every
slider and pattern, locks, swaps and the chosen alternative - without regenerating."""
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from orchsketch import patterns as pat
from orchsketch import project as pj
from orchsketch.edits import regenerate, swap
from orchsketch.generator import MELODY_ID, Settings, generate_all
from orchsketch.midi_io import read_chord_file
from orchsketch.theory import Key
from test_generator import EXPECTED, load
from test_motion import files_for

DATA = Path(__file__).parent / "data"


# ---------------------------------------------------------------- encoding
def test_values_come_back_with_their_exact_types():
    from orchsketch.analysis.chords import ChordLabel
    from orchsketch.midi_io import Note
    v = {"t": (1, (2, None)), "l": [1, [2]], "s": {3, 1}, "fs": frozenset({"a"}), "b": b"\x00\xff",
         "n": Note(60, 0, 480, 90), "k": Key("Eb", "minor"), "c": ChordLabel(0, "m7", 3), 4: "int key",
         "f": 0.1 + 0.2, "__odd": 1}
    back = pj.decode(json.loads(json.dumps(pj.encode(v))))
    assert back == v
    assert type(back["t"]) is tuple and type(back["l"]) is list and type(back["fs"]) is frozenset


def test_unknown_types_are_refused():
    with pytest.raises(TypeError):
        pj.encode(object())
    with pytest.raises(pj.ProjectError, match="doesn't know"):
        pj.decode({"__c": "Nope", "f": {}})


@pytest.fixture(scope="module")
def rich():
    """Test 11 with melody and bass files, moderate, 8ths, a part pattern, a regenerated and a swapped chord."""
    chords, key = load(EXPECTED[10])
    mel, bass = files_for(EXPECTED[10])
    st = Settings(melody=mel, bass=bass, pattern=pat.EIGHTHS, character="moderate",
                  part_patterns=(("hn2", pat.STABS),), section_dynamics=(("brass", "ff"),))
    alts = generate_all(chords, key, seed=2, settings=st)
    a = swap(regenerate(alts["A"], frozenset({"vln1-b"})), alts["B"], [2, 3])
    return chords, key, {"A": a, "B": alts["B"], "C": alts["C"]}


def make_project(rich, **kw):
    chords, key, alts = rich
    clip = read_chord_file(DATA / "11_sixteen_bars.mid")
    data = (DATA / "11_sixteen_bars.mid").read_bytes()
    mel = (DATA / "11_sixteen_bars.melody.mid").read_bytes()
    return pj.Project(pj.InputFile("11_sixteen_bars.mid", data), clip, tempo=96,
                      melody=pj.InputFile("11_sixteen_bars.melody.mid", mel, alts["A"].settings.melody),
                      alts=(alts["A"], alts["B"], "C couldn't be built"), locks=(frozenset({"vln1-b"}), frozenset(),
                                                                                    frozenset()), tab=1, **kw)


def test_project_file_round_trips_exactly(rich, tmp_path):
    p = make_project(rich, values=(("brass", "dynamics", "ff"),), ppatterns=(("hn2", pat.STABS),))
    path = pj.save(p, tmp_path / "Night Rise")
    assert path.name == "Night Rise.osk" and not list(tmp_path.glob("*.tmp"))
    q = pj.load(path)
    assert q == p
    a, b = p.alts[0], q.alts[0]
    assert [x.notes for x in a.parts] == [x.notes for x in b.parts]
    assert b.meta["origin"] == a.meta["origin"] and b.sources == a.sources  # swaps survive
    assert b.meta["previous"] == a.meta["previous"]  # Regenerate keeps steering away after reopening
    assert b.part(MELODY_ID).notes == a.part(MELODY_ID).notes and b.figures == a.figures
    assert q.melody.data == (DATA / "11_sixteen_bars.melody.mid").read_bytes()  # embedded copy


def test_notes_are_restored_even_if_the_generator_changes(rich, tmp_path, monkeypatch):
    """SPEC §7: reopening restores the saved notes exactly, even after app updates change the generator."""
    import orchsketch.generator as g
    p = make_project(rich)
    path = pj.save(p, tmp_path / "x.osk")
    for name in ("_render", "_generate", "_finish", "rerender"):
        monkeypatch.setattr(g, name, lambda *a, **k: pytest.fail("reopening must not regenerate or re-render"))
    q = pj.load(path)
    assert q.alts[0] == p.alts[0] and q.alts[1] == p.alts[1]


def test_bad_and_newer_files_get_a_clear_message(rich, tmp_path):
    bad = tmp_path / "bad.osk"
    bad.write_text("{nope", encoding="utf-8")
    with pytest.raises(pj.ProjectError, match="valid JSON"):
        pj.load(bad)
    bad.write_text('{"format": "other"}', encoding="utf-8")
    with pytest.raises(pj.ProjectError, match="isn't an OrchSketch project"):
        pj.load(bad)
    doc = pj.to_json(make_project(rich))
    doc["format_version"] = pj.FORMAT_VERSION + 1
    with pytest.raises(pj.ProjectError, match="newer"):
        pj.from_json(doc)


def test_older_and_newer_fields_are_tolerated(rich):
    doc = pj.to_json(make_project(rich))
    doc["project"]["some_future_setting"] = 3  # written by a later version: skipped
    del doc["project"]["scope"]  # missing in an older file: default
    q = pj.from_json(json.loads(json.dumps(doc)))
    assert q.scope == "all" and q.tempo == 96


# ---------------------------------------------------------------- the window
pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _window(tmp_path):
    from test_ui_smoke import make_window
    return make_window(tmp_path)


def _build_session(w):
    """Test 1 with melody and bass, a correction, mixed section sliders, patterns, a lock and a swap."""
    w.set_key("A", "minor")
    assert w.load(DATA / "01_epic_staple.mid")
    assert w.load_part_file("melody", DATA / "01_epic_staple.melody.mid")
    assert w.load_part_file("bass", DATA / "01_epic_staple.bass.mid")
    assert w.type_chord(0, "Am7") is None  # a correction
    w.confirm_all()
    w.set_scope("brass")
    w._slider_moved("dynamics", "ff")
    w._slider_moved("character", "moderate")
    w.set_scope("strings")
    w._slider_moved("pattern", pat.EIGHTHS)
    w.set_scope("all")
    w.tempo.setValue(118)
    w.seed.setValue(3)
    w.generate()
    assert w.orch is not None
    line = next(ln.id for ln in w.orch.sounding_lines if ln.id.startswith("hn"))
    w.set_part_pattern(line, pat.STABS)
    w.set_lock("vc", True)
    w.swap_from("B", 1)
    w.set_tab(2)
    return w


def test_save_and_reopen_in_the_window(app, tmp_path):
    w = _build_session(_window(tmp_path))
    before = w.snapshot()
    assert w.has_unsaved_changes() and w.windowTitle().endswith(" *")
    path = w.save_project()
    assert path == tmp_path / "Projects" / "01_epic_staple.osk" and path.exists()
    assert not w.has_unsaved_changes() and not w.windowTitle().endswith("*")
    files_a = {f.name: f.read_bytes() for f in w.files_for_all()}

    v = _window(tmp_path / "v")
    assert v.load(path)
    assert v.snapshot() == before  # every slider, pattern, file, correction, lock, swap and the tab
    assert v.tab == 2 and v.tempo.value() == 118 and v.seed.value() == 3
    assert v.values["brass"]["dynamics"] == "ff" and v.values["strings"]["pattern"] == pat.EIGHTHS
    assert v.melody_file[2] == (DATA / "01_epic_staple.melody.mid").read_bytes()
    assert v.locks[0] == frozenset({"vc"}) and v.alts[0].sources[1] == "B"
    assert v.project_name() == "01_epic_staple" and not v.has_unsaved_changes()
    assert {f.name: f.read_bytes() for f in v.files_for_all()} == files_a  # identical exports
    # it keeps working after reopening: an edit, then undo back to the saved state is clean again
    v.set_tab(0)
    v.regenerate_unlocked()
    assert v.has_unsaved_changes()
    v.undo()
    v.undo()
    assert v.tab == 2 and not v.has_unsaved_changes()
    w.close()
    v.close()


def test_save_prompt_before_discarding(app, tmp_path):
    w = _window(tmp_path)
    w.set_key("A", "minor")
    assert w.load(DATA / "01_epic_staple.mid")
    w.confirm_all()
    asked = []
    w.ask_save = lambda: asked.append(1) or "cancel"
    assert w.load(DATA / "02_basic_major.mid")  # nothing generated yet: no prompt
    w.set_key("C", "major")
    w.confirm_all()
    w.generate()
    assert not w.load(DATA / "03_natural_minor.mid") and asked == [1]  # cancel keeps the work
    assert w.project_name() == "02_basic_major"
    w.ask_save = lambda: "save"
    assert w.load(DATA / "03_natural_minor.mid")  # saved first, then opened
    assert (tmp_path / "Projects" / "02_basic_major.osk").exists()
    assert w.new_project() and w.session is None
    w.close()


def test_project_name_goes_into_export_names(app, tmp_path):
    w = _window(tmp_path)
    w.set_key("A", "minor")
    assert w.load(DATA / "01_epic_staple.mid")
    w.confirm_all()
    w.generate()
    w.ask_save_path = lambda default: tmp_path / "Night Rise.osk"
    w.save_project_as()
    w.export_box.setCurrentIndex(w.export_box.findData("both"))
    names = {f.name for f in w.files_for_all()}
    assert "Night_Rise_Full_A.mid" in names and "Night_Rise_Vln1-a_A.mid" in names
    w.combined_box.setChecked(True)
    assert "Night_Rise_Hn-all_A.mid" in {f.name for f in w.files_for_all()}
    w.close()


def test_damaged_project_is_refused_cleanly(app, tmp_path):
    notes = []
    from test_ui_smoke import make_window
    w = make_window(tmp_path, notes)
    bad = tmp_path / "bad.osk"
    bad.write_text("{}", encoding="utf-8")
    assert not w.load(bad) and notes and w.session is None
    w.close()
