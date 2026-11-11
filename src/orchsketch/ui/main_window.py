"""Milestone 1 main window: load a chord clip, review/correct labels, re-export.

Later milestones add the instrument grid, sliders, playback and orchestration export.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QCursor, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from .. import __version__
from ..analysis import AnalysisSession, ChordLabel, SymbolError, parse_symbol
from ..midi_io import InputError, read_chord_file, write_notes
from ..theory import MAJOR_TONICS, MINOR_TONICS, Key, note_name
from .chord_strip import ChordStrip, length_text
from .theme import MUTED

DOCS = Path.home() / "Documents" / "OrchSketch"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"OrchSketch {__version__}")
        self.resize(1200, 560)
        self.setAcceptDrops(True)
        self.settings = QSettings("OrchSketch", "OrchSketch")
        self.name_style = self.settings.value("note_names", "ableton")
        self.session: AnalysisSession | None = None
        self.selected: int | None = None
        self._build()

    # ------------------------------------------------------------------ layout
    def _build(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)

        bar = QHBoxLayout()
        self.open_btn = QPushButton("Open chords…")
        self.open_btn.clicked.connect(self.open_dialog)
        self.file_label = QLabel("No file")
        self.file_label.setStyleSheet(f"color: {MUTED};")
        self.tonic = QComboBox()
        self.mode = QComboBox()
        self.mode.addItems(["minor", "major"])
        self._fill_tonics("A")
        self.mode.currentTextChanged.connect(self._mode_changed)
        self.tonic.currentTextChanged.connect(self._key_changed)
        self.tempo = QSpinBox()
        self.tempo.setRange(20, 300)
        self.tempo.setValue(140)
        self.tempo.setSuffix(" BPM")
        self.confirm_btn = QPushButton("Confirm all")
        self.confirm_btn.clicked.connect(self.confirm_all)
        self.export_btn = QPushButton("Export MIDI…")
        self.export_btn.clicked.connect(self.export_dialog)
        for w in (self.open_btn, self.file_label):
            bar.addWidget(w)
        bar.addStretch(1)
        for label, w in (("Key", self.tonic), (None, self.mode), ("Tempo", self.tempo)):
            if label:
                bar.addWidget(QLabel(label))
            bar.addWidget(w)
        bar.addSpacing(16)
        bar.addWidget(self.confirm_btn)
        bar.addWidget(self.export_btn)
        root.addLayout(bar)

        self.strip = ChordStrip()
        self.strip.cell_clicked.connect(self.chord_clicked)
        root.addWidget(self.strip)

        legend = QLabel(
            "Click a chord to confirm or change it.   Border:  grey = best guess · "
            "<span style='color:#4caf50'>green</span> = confirmed · "
            "<span style='color:#5b9bd5'>blue</span> = corrected · "
            "<span style='color:#e05252'>red</span> = not recognized, set by hand.   ped = pedal tone"
        )
        legend.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        root.addWidget(legend)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        root.addWidget(self.details, 1)
        self.setCentralWidget(central)
        self.status_label = QLabel("")
        self.statusBar().addWidget(self.status_label, 1)
        self._menus()
        self._refresh()

    def _menus(self):
        m = self.menuBar().addMenu("&File")
        for text, slot, sc in (("&Open chords…", self.open_dialog, QKeySequence.Open),
                               ("&Export MIDI…", self.export_dialog, QKeySequence("Ctrl+E")),
                               ("&Quit", self.close, QKeySequence.Quit)):
            a = QAction(text, self)
            a.setShortcut(sc)
            a.triggered.connect(slot)
            m.addAction(a)
        v = self.menuBar().addMenu("&View")
        group = QActionGroup(self)
        for style, text in (("ableton", "Ableton note names (middle C = C3)"),
                            ("scientific", "Scientific note names (middle C = C4)")):
            a = QAction(text, self, checkable=True)
            a.setChecked(self.name_style == style)
            a.triggered.connect(lambda _=False, s=style: self.set_name_style(s))
            group.addAction(a)
            v.addAction(a)
        h = self.menuBar().addMenu("&Help")
        a = QAction("&About", self)
        a.triggered.connect(lambda: QMessageBox.about(
            self, "OrchSketch", f"OrchSketch {__version__}\nMilestone 1: read and label."))
        h.addAction(a)

    def _fill_tonics(self, current: str):
        tonics = MINOR_TONICS if self.mode.currentText() == "minor" else MAJOR_TONICS
        self.tonic.blockSignals(True)
        self.tonic.clear()
        self.tonic.addItems(list(tonics))
        idx = self.tonic.findText(current)
        self.tonic.setCurrentIndex(idx if idx >= 0 else 0)
        self.tonic.blockSignals(False)

    # ------------------------------------------------------------------ key
    def key(self) -> Key:
        return Key(self.tonic.currentText(), self.mode.currentText())

    def set_key(self, tonic: str, mode: str):
        self.mode.blockSignals(True)
        self.mode.setCurrentText(mode)
        self.mode.blockSignals(False)
        self._fill_tonics(tonic)
        self._key_changed()

    def _mode_changed(self, _):
        current = self.tonic.currentText()
        enh = {"Db": "C#", "C#": "Db", "Ab": "G#", "G#": "Ab"}
        tonics = MINOR_TONICS if self.mode.currentText() == "minor" else MAJOR_TONICS
        self._fill_tonics(current if current in tonics else enh.get(current, current))
        self._key_changed()

    def _key_changed(self, *_):
        if self.session:
            self.session.set_key(self.key())
        self._refresh()

    # ------------------------------------------------------------------ files
    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open block-chord MIDI", str(Path.home()),
                                              "MIDI files (*.mid *.midi)")
        if path:
            self.load(path)

    def load(self, path) -> bool:
        try:
            clip = read_chord_file(path)
        except InputError as exc:
            QMessageBox.warning(self, "Can't use this file", str(exc))
            return False
        self.session = AnalysisSession(clip, self.key())
        self.selected = None
        self.file_label.setText(f"{Path(path).name}  ·  {clip.bars} bars")
        self.file_label.setStyleSheet("")
        self._refresh()
        if clip.warnings:
            self.statusBar().showMessage(" ".join(dict.fromkeys(clip.warnings)), 10000)
        return True

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith((".mid", ".midi"))
                                          for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        for u in e.mimeData().urls():
            if u.toLocalFile().lower().endswith((".mid", ".midi")):
                self.load(u.toLocalFile())
                break

    def default_export_path(self) -> Path:
        stem = Path(self.session.clip.source_path).stem if self.session else "chords"
        return DOCS / "Exports" / stem / f"{stem}_reexport.mid"

    def export_dialog(self):
        if not self.session:
            QMessageBox.information(self, "Nothing to export", "Open a chord file first.")
            return
        target = self.default_export_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Export MIDI", str(target), "MIDI files (*.mid)")
        if path:
            self.export(path)

    def export(self, path) -> Path:
        """Plain re-export of the (grid-snapped) input notes, from bar 1, at the set tempo."""
        out = write_notes(path, self.session.clip.notes, self.tempo.value(), track_name="Chords",
                          length=self.session.clip.length)
        self.statusBar().showMessage(f"Exported {out}", 10000)
        return out

    # ------------------------------------------------------------------ chords
    def chord_clicked(self, index: int):
        # Defer: the clicked cell is still handling its mouse event, and _refresh() replaces it.
        QTimer.singleShot(0, lambda: self._open_chord(index))

    def _open_chord(self, index: int):
        self.selected = index
        self._refresh()
        r = self.session.results[index]
        if r.segment.is_rest:
            return
        self.show_menu(self.build_chord_menu(index))

    def show_menu(self, menu: QMenu):
        """Pop up a menu at the mouse (separate method so tests can replace it)."""
        menu.exec(QCursor.pos() + QPoint(4, 4))

    def build_chord_menu(self, index: int) -> QMenu:
        r = self.session.results[index]
        key = self.key()
        menu = QMenu(self)

        def add(text, fn):
            a = menu.addAction(text)
            a.triggered.connect(fn)
            return a

        if r.best is not None:
            mark = "✓ " if r.status == "confirmed" else ""
            add(f"{mark}{r.best.symbol(key)}  ·  {r.best.roman(key)}   (best guess)",
                lambda: self.apply_label(index, r.best))
        else:
            head = menu.addAction("Not recognized - pick or type a chord")
            head.setEnabled(False)
        if r.alternatives:
            menu.addSeparator()
            for alt in r.alternatives:
                add(f"{alt.symbol(key)}  ·  {alt.roman(key)}", lambda _=False, a=alt: self.apply_label(index, a))
        menu.addSeparator()
        add("Type a chord…", lambda: self.type_chord_dialog(index))
        if r.correction is not None:
            add("Back to best guess", lambda: self.revert(index))
        return menu

    def apply_label(self, index: int, label: ChordLabel):
        self.session.correct(index, label)
        self._refresh()

    def type_chord_dialog(self, index: int):
        r = self.session.results[index]
        current = r.label.symbol(self.key()) if r.label else ""
        text, ok = QInputDialog.getText(self, "Type a chord",
                                        "Chord symbol (e.g. Am7, C/E, Bbmaj7, F#m7b5, A5):", text=current)
        if ok and text.strip():
            err = self.type_chord(index, text)
            if err:
                QMessageBox.warning(self, "Chord not understood", err)

    def type_chord(self, index: int, text: str) -> str | None:
        """Apply a typed symbol. Returns an error message, or None if it worked."""
        try:
            self.apply_label(index, parse_symbol(text))
        except SymbolError as exc:
            return str(exc)
        return None

    def revert(self, index: int):
        self.session.revert(index)
        self._refresh()

    def confirm_all(self):
        if not self.session:
            return
        unset = self.session.confirm_all()
        self._refresh()
        if unset:
            QMessageBox.information(self, "Some chords need you",
                                    f"{unset} chord(s) weren't recognized. Click the red ones and set them by hand.")

    def set_name_style(self, style: str):
        self.name_style = style
        self.settings.setValue("note_names", style)
        self._refresh()

    # ------------------------------------------------------------------ display
    def _refresh(self):
        key = self.key()
        has = self.session is not None
        self.export_btn.setEnabled(has)
        self.confirm_btn.setEnabled(has)
        self.strip.show_results(self.session.results if has else [], key, self.selected)
        self.details.setHtml(self._details_html(key))
        if has:
            chords = self.session.chord_results
            n_conf = sum(r.confirmed for r in chords)
            n_unrec = sum(r.label is None for r in chords)
            msg = f"{len(chords)} chords · {n_conf} confirmed"
            if n_unrec:
                msg += f" · {n_unrec} need setting by hand"
            msg += "  ·  Key " + key.label()
            self.status_label.setText(msg)
        else:
            self.status_label.setText("Open or drop a block-chord MIDI file (4/4, up to 16 bars).")

    def _details_html(self, key: Key) -> str:
        if not self.session:
            return (f"<p style='color:{MUTED}'>Export the chord clip from Ableton (right-click the clip "
                    "&gt; Export MIDI Clip), then drop it here. Set the key and mode first or after - "
                    "labels update either way.</p>")
        if self.selected is None:
            return f"<p style='color:{MUTED}'>Click a chord to see its notes and alternatives.</p>"
        r = self.session.results[self.selected]
        seg = r.segment
        bar, beat = seg.start // 1920 + 1, (seg.start % 1920) / 480 + 1
        notes = ", ".join(note_name(p, self.name_style, key) for p in seg.pitches) or "(rest)"
        rows = [f"<b>Bar {bar}, beat {beat:g}</b> · {length_text(seg.length)}",
                f"Notes (low to high): {notes}"]
        if seg.pedal:
            rows.append(f"Pedal: {note_name(seg.bass, self.name_style, key)} held under the chord changes")
        if not seg.is_rest:
            lab = r.label
            rows.append(f"Label: <b>{lab.symbol(key)} · {lab.roman(key)}</b> ({r.status})" if lab
                        else "Label: <b style='color:#e05252'>not recognized</b> - set it by hand")
            if r.alternatives:
                rows.append("Alternatives: " + ", ".join(f"{a.symbol(key)} · {a.roman(key)}"
                                                         for a in r.alternatives))
        return "<br>".join(rows)
