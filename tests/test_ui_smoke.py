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


def test_generate_grid_play_mute_export(app, tmp_path):
    """Milestone 3: confirm, generate, grid, piano roll, playback (silent backend), mute/solo, export."""
    from test_player import FakeBackend

    from orchsketch.playback.player import Player

    notes = []
    w = MainWindow()
    w.notify = lambda title, text: notes.append((title, text))
    w.open_folder = lambda path: None
    w.export_root = tmp_path
    w.player_factory = lambda: Player(FakeBackend)
    w.set_key("A", "minor")
    assert w.load(DATA / "01_epic_staple.mid")
    assert not w.generate_btn.isEnabled()
    assert w.generate() is None and "Confirm" in notes[-1][0]
    w.confirm_all()
    assert w.generate_btn.isEnabled()
    orch = w.generate()
    assert orch is not None and w.orch is orch
    assert w.grid.rowCount() == len(orch.lines) == 31
    assert w.grid.columnCount() == 3 + 4
    assert w.checker_label.text() == "Checker: no problems."
    assert w.reason_label.text().startswith("A · Low and warm")
    cell = w.grid.item(w.grid.line_ids.index("vc"), 3).text()
    assert cell == "A1"  # cellos on A2 (scientific) = A1 in Ableton names
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
    assert all(f.parent == tmp_path / "01_epic_staple" for f in files)
    assert {f.name for f in w.files_for_part("vln1-a")} == {"01_epic_staple_Vln1-a_A.mid"}

    # sections off -> fewer parts; changing a chord or the key clears the result
    w.section_boxes["choir"].setChecked(False)
    w.section_boxes["woodwinds"].setChecked(False)
    orch2 = w.generate()
    assert {ln.instrument for ln in orch2.lines}.isdisjoint({"flute", "choir_bass"})
    w.set_key("C", "major")
    assert w.orch is None and not w.play_btn.isEnabled()
    w.close()
    assert w.player.backend is None
