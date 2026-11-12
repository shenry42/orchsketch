"""Off-screen UI smoke test. Runs where PySide6 is installed (your PC); skipped elsewhere."""
import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from orchsketch.midi_io import read_chord_file  # noqa: E402
from orchsketch.ui.main_window import MainWindow  # noqa: E402
from orchsketch.ui.theme import apply_dark_theme  # noqa: E402

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication([])
    apply_dark_theme(a)
    return a


def test_load_label_correct_export(app, tmp_path):
    exp = json.loads((DATA / "12_power_and_ambiguous.expected.json").read_text(encoding="utf-8"))
    w = MainWindow()
    w.set_key(exp["key"]["tonic"], exp["key"]["mode"])
    assert w.load(DATA / exp["file"])
    assert len(w.strip.cells) == len(exp["chords"])
    assert w.session.results[0].label.symbol(w.key()) == "A5"
    menu = w.build_chord_menu(4)  # Am7: best guess + alternatives + type + ...
    texts = [a.text() for a in menu.actions() if a.text()]
    assert any("C6/A" in t for t in texts)
    assert w.type_chord(4, "C6/A") is None
    assert w.session.results[4].status == "corrected"
    assert w.type_chord(4, "C13") is not None  # not in the v1 vocabulary
    w.revert(4)
    w.confirm_all()
    assert w.session.all_confirmed
    w.selected = 0
    w._refresh()
    assert "A1" in w.details.toPlainText()  # A2 scientific = A1 in Ableton names
    out = w.export(tmp_path / "re.mid")
    assert read_chord_file(out).notes == w.session.clip.notes
    w.set_key("C", "major")
    assert w.session.results[0].label.roman(w.key()) == "vi5"  # A5 in C major sits on the vi degree
    w.close()


def test_bad_file_is_rejected_cleanly(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    bad = tmp_path / "bad.mid"
    bad.write_bytes(b"nope")
    w = MainWindow()
    assert not w.load(bad) and shown and w.session is None
    w.close()


def test_clicking_a_cell_opens_menu_without_errors(app, monkeypatch):
    """Regression (v0.1 testing): clicking a chord rebuilt the strip and the click
    handler then touched the deleted cell -> 'Internal C++ object already deleted'."""
    import sys

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    errors = []
    monkeypatch.setattr(sys, "excepthook", lambda *a: errors.append(a[1]))
    opened = []
    w = MainWindow()
    w.show_menu = opened.append  # never block on a real popup in tests
    w.set_key("G", "major")
    assert w.load(DATA / "06_inversions.mid")
    w.show()
    for i in range(4):
        QTest.mouseClick(w.strip.cells[i], Qt.LeftButton)
        for _ in range(3):
            app.processEvents()
        assert w.selected == i
    assert len(opened) == 4 and not errors, errors
    w.close()


def make_window(tmp_path, notes=None):
    from test_player import FakeBackend

    from orchsketch.playback.player import Player
    w = MainWindow()
    w.run_async = False
    w.notify = lambda title, text: (notes if notes is not None else []).append((title, text))
    w.open_folder = lambda path: None
    w.show_menu = lambda menu: None  # never block on a real popup in tests
    w.ask_save = lambda: "discard"  # never block on the save prompt in tests
    from PySide6.QtCore import QSettings
    w.settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)  # never touch the real ones
    w.export_box.setCurrentIndex(w.export_box.findData("parts"))
    w.combined_box.setChecked(False)
    w.ask_save_path = lambda default: tmp_path / "Projects" / default.name
    w.projects_root = tmp_path / "Projects"
    w.export_root = tmp_path / "Exports"
    w.presets_folder = tmp_path / "Presets"
    w.player_factory = lambda: Player(FakeBackend)
    return w


def test_generate_grid_play_mute_export(app, tmp_path):
    """Milestone 3 flow, now with three alternatives: confirm, generate, grid, piano roll, playback
    (silent backend), mute/solo, export."""
    notes = []
    w = make_window(tmp_path, notes)
    w.set_key("A", "minor")
    assert w.load(DATA / "01_epic_staple.mid")
    assert not w.generate_btn.isEnabled()
    assert w.generate() is None and "Confirm" in notes[-1][0]
    w.confirm_all()
    assert w.generate_btn.isEnabled()
    orch = w.generate()
    assert orch is not None and w.orch is orch and orch.approach == "A"
    assert all(o is not None and not isinstance(o, str) for o in w.alts)
    assert w.grid.rowCount() == len(orch.sounding_lines) == 31
    assert w.grid.columnCount() == 4 + 4
    assert w.checker_label.text() == "Checker: no problems."
    assert w.reason_label.text().startswith("A · Low and warm")
    cell = w.grid.item(w.grid.line_ids.index("vc"), 4).text()
    assert cell == "A1 ♪"  # cellos on A2 (scientific) = A1 in Ableton names; ♪: Full epic's 8th ostinato
    w.grid.select_part("vc")
    assert w.piano.title == "Cellos" and w.piano.notes

    assert w.play() and w.player.playing
    w.player._tick()
    w.grid.mute_buttons["vc"].setChecked(True)
    assert not w.player.seq.audible("vc")
    w.section_solo["brass"].setChecked(True)
    assert w.player.seq.audible("hn1") and not w.player.seq.audible("vla")
    w.stop()
    assert not w.player.playing and w.player.seq.sounding() == {}

    files = w.export_parts_action()
    assert len(files) == sum(1 for p in orch.parts if p.notes)
    assert all(f.parent == tmp_path / "Exports" / "01_epic_staple" for f in files)
    assert {f.name for f in w.files_for_part("vln1-a")} == {"01_epic_staple_Vln1-a_A.mid"}
    w.set_tab(2)
    assert w.reason_label.text().startswith("C · High and bright")
    assert {f.name for f in w.files_for_part("picc")} == {"01_epic_staple_Picc_C.mid"}

    # fewer instruments -> fewer parts; changing a chord or the key clears the result
    w.set_instrument("flute", False)
    w.set_preset("strings_horns")
    assert w.dirty and "•" in w.generate_btn.text()
    w.generate()
    assert {ln.instrument for ln in w.orch.sounding_lines} <= {"violins_1", "violins_2", "violas", "cellos",
                                                               "basses", "horn"}
    assert not w.dirty
    w.set_key("C", "major")
    assert w.orch is None and not w.play_btn.isEnabled()
    w.close()
    assert w.player.backend is None


def test_milestone_4_controls(app, tmp_path):
    """Tabs, lock + regenerate, part and chord menus, swap, undo/redo, sliders, presets, keep-as-is."""
    notes = []
    w = make_window(tmp_path, notes)
    w.set_key("A", "minor")
    assert w.load(DATA / "01_epic_staple.mid")
    w.confirm_all()
    a = w.generate()
    # tabs
    w.tabs.setCurrentIndex(1)
    assert w.orch.approach == "B" and w.reason_label.text().startswith("B · Wide and full")
    w.tabs.setCurrentIndex(0)
    # lock + regenerate unlocked
    w.grid.lock_buttons["vln1-a"].setChecked(True)
    assert w.locks[0] == {"vln1-a"} and w.locks[1] == frozenset()
    r = w.regenerate_unlocked()
    assert r is not None and r.cells["vln1-a"] == a.cells["vln1-a"] and r.cells != a.cells
    assert w.grid.lock_buttons["vln1-a"].isChecked()  # still shown locked
    # part menu: lock + regenerate this part; column menu: regenerate chord + swaps
    texts = [x.text() for x in w.build_part_menu("hn2", 1).actions()]
    assert "Regenerate Horn 2 only" in texts and "Use B's voicing for this chord" in texts
    assert w.regenerate_one_part("hn2").cells["hn2"] != r.cells["hn2"]
    before = w.orch
    w.regenerate_one_chord(2)
    assert w.orch is not before
    w.swap_from("B", 1)
    assert w.orch.sources[1] == "B" and "· B" in w.grid.horizontalHeaderItem(4 + 1).text()
    menu_texts = [x.text() for x in w.build_column_menu(1).actions()]
    assert any("back to own" in t for t in menu_texts)
    w.swap_from("A", 1)  # back to own
    assert w.orch.sources[1] == "A"
    # undo / redo through all of it
    n_steps = w.history.pos
    w.undo()  # the swap back
    assert w.orch.sources[1] == "B"
    w.undo()  # the swap
    w.undo()  # regenerate chord
    w.undo()  # regenerate Horn 2
    assert w.orch is r
    w.undo()  # regenerate unlocked
    assert w.orch is a and w.locks[0] == frozenset({"vln1-a"})
    w.undo()  # the lock
    assert w.orch is a and w.locks[0] == frozenset() and not w.grid.lock_buttons["vln1-a"].isChecked()
    for _ in range(n_steps):
        w.redo()
    assert w.history.pos == n_steps and w.orch.sources[1] == "A"
    # dynamics apply at once; forces/density wait for Generate
    w.dynamics.setValue(5)
    assert all(o.velocity == 120 for o in w.alts) and not w.dirty
    w.undo()
    assert all(o.velocity == 80 for o in w.alts)
    w.density.setValue(0)
    assert w.dirty and w.orch is not None
    w.generate()
    assert len(w.orch.sounding_lines) < len(a.sounding_lines)
    # corrections are undoable too, and clear the alternatives
    w.type_chord(1, "Dm")
    assert w.orch is None
    w.undo()
    assert w.orch is not None and w.session.results[1].correction is None
    # presets: save your own, pick a built-in
    w.set_instrument("piccolo", False)
    assert w.preset_box.currentData() == "custom"
    mine = w.save_current_preset("No piccolo")
    assert (tmp_path / "Presets" / f"{mine.id}.json").exists() and w.preset_box.currentData() == mine.id
    w.set_preset("brass_choir")
    assert "violins_1" not in w.active and w.dynamics.value() == 4  # f
    # keep-as-is and top voice
    w.set_preset("full_epic")
    w.keep_box.setChecked(True)
    w.top_box.setCurrentIndex(1)
    w.generate()
    assert w.orch.settings.keep is not None and w.orch.settings.top_voice == "input"
    kept = [ln.id for ln in w.orch.sounding_lines if ln.id.startswith("k-")]
    assert kept and w.reason_label.text().split(": ", 1)[1].startswith("your voicing kept")
    assert not notes, notes
    w.close()


def test_generate_runs_in_the_background(app, tmp_path):
    w = make_window(tmp_path)
    w.run_async = True
    w.set_key("A", "minor")
    assert w.load(DATA / "11_sixteen_bars.mid")
    w.confirm_all()
    assert w.generate() is None  # started, not finished
    assert not w.generate_btn.isEnabled() and w.generate_btn.text() == "Generating…"
    w.wait_for_generation()
    assert w.orch is not None and all(o is not None for o in w.alts) and w.generate_btn.isEnabled()
    w.close()


def test_milestone_5_controls(app, tmp_path):
    """Melody and bass slots, patterns (section scope, per part), per-section dynamics, Character, independent
    bass, re-strike, presets with sections, and undo through all of it."""
    notes = []
    w = make_window(tmp_path, notes)
    w.set_key("A", "minor")
    assert w.load(DATA / "01_epic_staple.mid")
    w.confirm_all()
    assert not w.mel_inst_box.isEnabled() and w.indep_box.isEnabled()
    assert w.load_part_file("melody", DATA / "01_epic_staple.melody.mid")
    assert w.load_part_file("bass", DATA / "01_epic_staple.bass.mid")
    assert w.slot_label["melody"].text() == "01_epic_staple.melody.mid" and w.mel_inst_box.isEnabled()
    assert not w.indep_box.isEnabled()  # a bass file is loaded
    o = w.generate()
    assert "mel" in o.cells and "melody in the" in w.reason_label.text()
    assert "bass line from your file" in o.reason and o.part("vc").notes[0].end < 960  # the file's rhythm
    labels = w.grid.row_labels
    assert labels["vc"].endswith("· bass file") and labels["vln2"].endswith("· 8ths")  # Full epic: strings 8ths
    assert labels["tba"].endswith("bass file")  # tuba plays the file, not its preset half-time pulse
    menu = w.build_part_menu("mel", 0)
    regen = next(a for a in menu.actions() if a.text().startswith("Regenerate") and "only" in a.text())
    assert not regen.isEnabled()
    # patterns: brass section to 16ths applies at once (no Generate needed)
    w.set_scope("brass")
    i = w.pattern_box.findData("16ths")
    w.pattern_box.setCurrentIndex(i)
    w.pattern_box.activated.emit(i)
    assert not w.dirty and len(w.orch.part("hn1").notes) > len(o.part("hn1").notes)
    assert w.orch.cells == o.cells
    # one part on its own pattern, then undo
    w.set_part_pattern("hn2", "stabs")
    assert [n.start for n in w.orch.part("hn2").notes][:2] == [0, 720]
    w.undo()
    assert len(w.orch.part("hn2").notes) == len(w.orch.part("hn1").notes)
    # per-section dynamics: brass ff, strings stay mf
    w.dynamics.setValue(5)
    assert {n.velocity for n in w.orch.part("hn1").notes} <= {120, 96} and w.orch.cc1_for("vln2") == 80
    assert "ff" in w.dynamics_label.text()
    w.set_scope("all")
    assert "differ" in w.dynamics_label.text()
    # Character waits for Generate
    w.character.setValue(1)
    assert w.dirty and w.character_label.text().startswith("Moderate")
    w.generate()
    assert w.orch.mode == "moderate"
    # remove the bass file: the independent bass becomes available
    w.clear_part_file("bass")
    assert w.indep_box.isEnabled() and w.bass_file is None
    w.indep_box.setChecked(True)
    w.generate()
    assert w.orch.meta["info"].get("bass") == "independent"
    w.undo()
    w.undo()
    w.undo()
    assert w.bass_file is not None and not w.indep_box.isChecked()
    # re-strike every bar applies at once
    w.restrike_box.setChecked(True)
    assert w.orch.settings.restrike_bars and not w.dirty
    # presets keep per-section values and patterns
    mine = w.save_current_preset("Brass loud")
    assert dict(mine.patterns).get("brass") == "16ths" and ("brass", "dynamics", "ff") in mine.sections
    w.set_preset("strings_only")
    assert w.values["brass"]["dynamics"] == "mf" and w.values["strings"]["pattern"] == "sustain"
    w.set_preset(mine.id)
    assert w.values["brass"]["dynamics"] == "ff" and w.values["brass"]["pattern"] == "16ths"
    assert w.values["strings"]["pattern"] == "8ths"
    # a bad melody file is refused with a message
    assert not w.load_part_file("melody", DATA / "01_epic_staple.mid") and "Can't use" in notes[-1][0]
    w.close()


def test_piano_roll_writes_note_names(app, tmp_path):
    """v1.0 (Sam): the piano roll shows each note's name (Ableton names by default), once per repeated note."""
    from orchsketch.midi_io import Note
    w = make_window(tmp_path)
    w.set_key("A", "minor")
    assert w.load(DATA / "01_epic_staple.mid")
    w.confirm_all()
    w.generate()
    w.show_part("vc")
    names = [t for _, t in w.piano.labels()]
    assert names and names[0] == "A1"  # cellos on A2 (scientific) = A1 in Ableton names
    w.piano.set_part("x", [Note(60, 0, 240), Note(60, 240, 480), Note(62, 480, 960), Note(60, 960, 1200)], 1920,
                     [0], "scientific", w.key())
    assert [t for _, t in w.piano.labels()] == ["C4", "D4", "C4"]  # the repeated C isn't labelled twice
    w.show()
    w.piano.repaint()  # paints without errors
    w.close()
