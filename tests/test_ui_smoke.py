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
