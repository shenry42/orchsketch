"""Main window: load a chord clip, review/correct labels, generate, audition and export.

Milestone 3 adds section toggles, Generate, the part grid, the piano-roll preview, playback and per-part
export. Later milestones add alternatives, locks, sliders and presets.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QCursor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMenu,
    QMessageBox, QPushButton, QSpinBox, QSplitter, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__
from ..analysis import AnalysisSession, ChordLabel, SymbolError, parse_symbol
from ..checker import chords_from_session
from ..export import EXPORT_ROOT, export_folder, export_part, export_parts
from ..generator import Ensemble, GenerationError, Orchestration, generate
from ..instruments import SECTIONS, instruments
from ..midi_io import InputError, read_chord_file, write_notes
from ..playback.player import Player
from ..playback.synth import SynthError
from ..theory import MAJOR_TONICS, MINOR_TONICS, Key, note_name
from .chord_strip import ChordStrip, length_text
from .grid import DragHandle, PartGrid, PianoRoll
from .theme import MUTED

DOCS = Path.home() / "Documents" / "OrchSketch"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"OrchSketch {__version__}")
        self.resize(1280, 820)
        self.setAcceptDrops(True)
        self.settings = QSettings("OrchSketch", "OrchSketch")
        self.name_style = self.settings.value("note_names", "ableton")
        self.session: AnalysisSession | None = None
        self.selected: int | None = None
        self.orch: Orchestration | None = None
        self.player: Player | None = None
        self.player_factory = Player  # tests replace this with a silent backend
        self.muted: set[str] = set()
        self.soloed: set[str] = set()
        self.export_root = EXPORT_ROOT
        self._build()
        self.playhead = QTimer(self)
        self.playhead.setInterval(50)
        self.playhead.timeout.connect(self._update_playhead)

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
        self.tempo.valueChanged.connect(self._tempo_changed)
        self.confirm_btn = QPushButton("Confirm all")
        self.confirm_btn.clicked.connect(self.confirm_all)
        self.section_boxes: dict[str, QCheckBox] = {}
        for sec in SECTIONS:
            cb = QCheckBox(sec.capitalize())
            cb.setChecked(True)
            cb.setToolTip(f"Include the {sec} in the orchestration")
            self.section_boxes[sec] = cb
        self.seed = QSpinBox()
        self.seed.setRange(1, 9999)
        self.seed.setValue(1)
        self.seed.setToolTip("Same chords, sections and seed always give the same result")
        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setStyleSheet("QPushButton { font-weight: 600; }")
        self.generate_btn.clicked.connect(self.generate)
        for w in (self.open_btn, self.file_label):
            bar.addWidget(w)
        bar.addStretch(1)
        for label, w in (("Key", self.tonic), (None, self.mode), ("Tempo", self.tempo)):
            if label:
                bar.addWidget(QLabel(label))
            bar.addWidget(w)
        bar.addSpacing(16)
        bar.addWidget(self.confirm_btn)
        bar.addSpacing(16)
        for cb in self.section_boxes.values():
            bar.addWidget(cb)
        bar.addWidget(QLabel("Seed"))
        bar.addWidget(self.seed)
        bar.addWidget(self.generate_btn)
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
        self.grid = PartGrid(self.files_for_part)
        self.grid.part_selected.connect(self.show_part)
        self.grid.mute_toggled.connect(self.set_mute)
        self.grid.solo_toggled.connect(self.set_solo)
        self.piano = PianoRoll()
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.grid)
        split.addWidget(self.piano)
        split.addWidget(self.details)
        split.setSizes([420, 120, 90])
        root.addWidget(split, 1)

        tr = QHBoxLayout()
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self.toggle_play)
        self.loop_box = QCheckBox("Loop")
        self.loop_box.setChecked(True)
        self.loop_box.toggled.connect(self._loop_changed)
        tr.addWidget(self.play_btn)
        tr.addWidget(self.loop_box)
        tr.addSpacing(16)
        self.section_mute: dict[str, QToolButton] = {}
        self.section_solo: dict[str, QToolButton] = {}
        for sec in SECTIONS:
            tr.addWidget(QLabel(sec.capitalize()))
            for kind, store, color in (("M", self.section_mute, "#e0a040"), ("S", self.section_solo, "#60c060")):
                b = QToolButton()
                b.setText(kind)
                b.setCheckable(True)
                b.setToolTip(f"{'Mute' if kind == 'M' else 'Solo'} the {sec}")
                b.setStyleSheet(f"QToolButton:checked {{ background: {color}; color: #111; }}")
                b.toggled.connect(lambda on, s=sec, k=kind: self.set_section(s, k, on))
                store[sec] = b
                tr.addWidget(b)
            tr.addSpacing(8)
        tr.addStretch(1)
        self.all_handle = DragHandle(self.files_for_all, "⠿ All", "Drag every part into Ableton")
        self.all_handle.setStyleSheet("padding: 4px 10px; border: 1px solid #555; border-radius: 4px;")
        self.export_parts_btn = QPushButton("Export parts")
        self.export_parts_btn.setToolTip("Save one MIDI file per part to Documents\\OrchSketch\\Exports")
        self.export_parts_btn.clicked.connect(self.export_parts_action)
        tr.addWidget(self.all_handle)
        tr.addWidget(self.export_parts_btn)
        root.addLayout(tr)
        self.checker_label = QLabel("")
        self.reason_label = QLabel("")
        self.reason_label.setStyleSheet(f"color: {MUTED};")
        info = QHBoxLayout()
        info.addWidget(self.checker_label)
        info.addSpacing(20)
        info.addWidget(self.reason_label, 1)
        root.addLayout(info)
        self.setCentralWidget(central)
        self.status_label = QLabel("")
        self.statusBar().addWidget(self.status_label, 1)
        self._menus()
        self._refresh()

    def _menus(self):
        m = self.menuBar().addMenu("&File")
        for text, slot, sc in (("&Open chords…", self.open_dialog, QKeySequence.Open),
                               ("&Generate", self.generate, QKeySequence("Ctrl+G")),
                               ("Export &parts", self.export_parts_action, QKeySequence("Ctrl+E")),
                               ("&Re-export input clip…", self.export_dialog, QKeySequence("Ctrl+Shift+E")),
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
            self, "OrchSketch", f"OrchSketch {__version__}\nMilestone 3: first orchestration."))
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
            self.clear_orchestration("The key changed - press Generate again.")
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
        self.clear_orchestration()
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
        self.clear_orchestration("A chord changed - press Generate again.")
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
        self.clear_orchestration("A chord changed - press Generate again.")
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
        if self.orch is not None:
            self.grid.show_orchestration(self.orch, self.key(), style)
        self._refresh()

    # ------------------------------------------------------------------ display
    def _refresh(self):
        key = self.key()
        has = self.session is not None
        self.confirm_btn.setEnabled(has)
        ready = has and self.session.all_confirmed and bool(self.session.chord_results)
        self.generate_btn.setEnabled(ready)
        self.generate_btn.setToolTip("Orchestrate the confirmed chords" if ready
                                     else "Confirm every chord first (Confirm all)")
        for w in (self.play_btn, self.export_parts_btn, self.all_handle):
            w.setEnabled(self.orch is not None)
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

    # ------------------------------------------------------------------ messages (replaceable in tests)
    def notify(self, title: str, text: str):
        QMessageBox.information(self, title, text)

    def open_folder(self, path: Path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ------------------------------------------------------------------ generate
    def active_sections(self) -> frozenset[str]:
        return frozenset(s for s, cb in self.section_boxes.items() if cb.isChecked())

    def generate(self) -> Orchestration | None:
        if not self.session:
            self.notify("Nothing to orchestrate", "Open a chord file first.")
            return None
        if not self.session.all_confirmed:
            self.notify("Confirm the chords first",
                        "Generation only uses confirmed chords. Click Confirm all (or confirm each chord).")
            return None
        secs = self.active_sections()
        if not secs:
            self.notify("No sections", "Tick at least one section (woodwinds, brass, strings or choir).")
            return None
        chords = chords_from_session(self.session)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            orch = generate(chords, self.key(), seed=self.seed.value(), ensemble=Ensemble(secs))
        except GenerationError as exc:
            QApplication.restoreOverrideCursor()
            self.notify("Couldn't orchestrate", str(exc))
            return None
        QApplication.restoreOverrideCursor()
        self.stop()
        self.orch = orch
        self.muted, self.soloed = set(), set()
        for b in list(self.section_mute.values()) + list(self.section_solo.values()):
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        self.grid.show_orchestration(orch, self.key(), self.name_style)
        if self.player is not None and self.player.seq is not None:
            self._load_player()
        self.checker_label.setText(orch.report.summary())
        self.reason_label.setText(f"A · {orch.reason}")
        self.piano.clear_part()
        self.grid.select_part(orch.lines[0].id)
        self._refresh()
        return orch

    def clear_orchestration(self, message: str | None = None):
        if self.orch is None:
            self.grid.clear_grid()
            return
        self.stop()
        self.orch = None
        self.grid.clear_grid(message or "Confirm the chords, then press Generate.")
        self.piano.clear_part()
        self.checker_label.setText("")
        self.reason_label.setText("")
        if self.player is not None:
            self.player.seq = None

    def show_part(self, line_id: str):
        if not self.orch:
            return
        ln = self.orch.line(line_id)
        self.piano.set_part(ln.label, self.orch.part(line_id).notes, self.session.clip.length,
                            [c.start for c in self.orch.chords], self.name_style)

    # ------------------------------------------------------------------ playback
    def _load_player(self):
        insts = instruments()
        parts = [(ln.id, insts[ln.instrument].gm_program, list(self.orch.part(ln.id).notes)) for ln in self.orch.lines]
        sections = {ln.id: insts[ln.instrument].section for ln in self.orch.lines}
        self.player.loop = self.loop_box.isChecked()
        self.player.set_bpm(self.tempo.value())
        self.player.load(parts, self.session.clip.length, sections)
        for pid in self.muted:
            self.player.seq.set_mute(pid, True)
        for pid in self.soloed:
            self.player.seq.set_solo(pid, True)

    def play(self) -> bool:
        if not self.orch:
            return False
        try:
            if self.player is None:
                self.player = self.player_factory()
                self.player.on_stopped = self._playback_ended
            if self.player.seq is None:
                self._load_player()
        except SynthError as exc:
            self.player = None
            self.notify("No audio", str(exc))
            return False
        self.player.play()
        self.play_btn.setText("■ Stop")
        self.playhead.start()
        return True

    def stop(self):
        if self.player is not None:
            self.player.stop()
        self.play_btn.setText("▶ Play")
        if hasattr(self, "playhead"):
            self.playhead.stop()
        self.piano.set_position(None)

    def toggle_play(self):
        if self.player is not None and self.player.playing:
            self.stop()
        else:
            self.play()

    def _playback_ended(self):
        self.stop()

    def _update_playhead(self):
        if self.player is not None and self.player.seq is not None and self.player.playing:
            self.piano.set_position(self.player.seq.pos)

    def _tempo_changed(self, bpm):
        if self.player is not None:
            self.player.set_bpm(bpm)

    def _loop_changed(self, on):
        if self.player is not None:
            self.player.loop = on

    def set_mute(self, line_id: str, on: bool):
        (self.muted.add if on else self.muted.discard)(line_id)
        if self.player is not None and self.player.seq is not None:
            self.player.seq.set_mute(line_id, on)

    def set_solo(self, line_id: str, on: bool):
        (self.soloed.add if on else self.soloed.discard)(line_id)
        if self.player is not None and self.player.seq is not None:
            self.player.seq.set_solo(line_id, on)

    def set_section(self, section: str, kind: str, on: bool):
        """Section mute/solo: toggles the row buttons of every part in that section."""
        if not self.orch:
            return
        insts = instruments()
        buttons = self.grid.mute_buttons if kind == "M" else self.grid.solo_buttons
        for ln in self.orch.lines:
            if insts[ln.instrument].section == section and ln.id in buttons:
                buttons[ln.id].setChecked(on)

    # ------------------------------------------------------------------ export
    def project_name(self) -> str:
        return Path(self.session.clip.source_path).stem if self.session else "OrchSketch"

    def parts_folder(self) -> Path:
        return export_folder(self.project_name(), self.export_root)

    def files_for_part(self, line_id: str) -> list[Path]:
        if not self.orch:
            return []
        p = export_part(self.orch, line_id, self.parts_folder(), self.project_name(), self.tempo.value(),
                        self.session.clip.length)
        return [p] if p else []

    def files_for_all(self) -> list[Path]:
        if not self.orch:
            return []
        return export_parts(self.orch, self.parts_folder(), self.project_name(), self.tempo.value(),
                            self.session.clip.length)

    def export_parts_action(self) -> list[Path]:
        if not self.orch:
            self.notify("Nothing to export", "Generate an orchestration first.")
            return []
        files = self.files_for_all()
        folder = self.parts_folder()
        self.statusBar().showMessage(f"Exported {len(files)} parts to {folder}", 15000)
        self.open_folder(folder)
        return files

    def closeEvent(self, e):  # noqa: N802
        if self.player is not None:
            self.player.close()
        super().closeEvent(e)
