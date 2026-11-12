"""Orchestration grid (SPEC §6, item 3) and piano-roll preview (item 5).

One row per sounding (or locked) part, one column per chord. Each cell shows the part's note (Ableton names
by default); a note held over from the previous identical chord shows "~". Yellow text = outside
comfortable range, red cell = a rule error (only after your own edits), orange cell = a checker warning
(hover for the reason). Each row has lock, mute, solo and a drag handle for export. Click a chord header
for the chord menu (regenerate, swap); right-click a row for the part menu (lock, regenerate this part).
A header like "Am · B" means that chord uses alternative B's voicing.
"""
from __future__ import annotations

from PySide6.QtCore import QMimeData, QPoint, QRectF, Qt, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QDrag, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QToolButton, QWidget,
)

from ..instruments import instruments
from ..midi_io import BAR
from ..theory import Key, note_name
from .theme import MUTED, PANEL, TEXT

SECTION_TINT = {"woodwinds": "#26302a", "brass": "#332c22", "strings": "#232b36", "choir": "#2f2636"}
YELLOW = "#e6c84f"
RED_BG = "#5a2323"
WARN_BG = "#4d3b1c"
LOCK_COLOR = "#5b9bd5"
CTRL_COLS = 4  # lock, mute, solo, drag


class DragHandle(QLabel):
    """Drag this into Ableton: it asks the window for the file(s) to drag, then starts a file drag."""

    def __init__(self, files_for_drag, text="⠿", tip="Drag into Ableton"):
        super().__init__(text)
        self.files_for_drag = files_for_drag  # callable -> list[Path]
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip(tip)
        self._press: QPoint | None = None

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._press is None or (e.position().toPoint() - self._press).manhattanLength() < \
                QApplication.startDragDistance():
            return
        self._press = None
        files = self.files_for_drag()
        if not files:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(f)) for f in files])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)

    def mouseReleaseEvent(self, e):  # noqa: N802
        self._press = None


class PartGrid(QTableWidget):
    part_selected = Signal(str)
    mute_toggled = Signal(str, bool)
    solo_toggled = Signal(str, bool)
    lock_toggled = Signal(str, bool)
    chord_menu_requested = Signal(int)  # chord index
    part_menu_requested = Signal(str, int)  # line id, chord index (-1 = row header)

    def __init__(self, files_for_part):
        super().__init__()
        self.files_for_part = files_for_part  # callable(line_id) -> list[Path]
        self.line_ids: list[str] = []
        self.mute_buttons: dict[str, QToolButton] = {}
        self.solo_buttons: dict[str, QToolButton] = {}
        self.lock_buttons: dict[str, QToolButton] = {}
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.horizontalHeader().sectionClicked.connect(self._header_clicked)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.verticalHeader().setDefaultSectionSize(22)
        self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.horizontalHeader().setMinimumSectionSize(28)
        self.setStyleSheet(f"QTableWidget {{ gridline-color: #3a3c42; background: {PANEL}; }}")
        self.itemSelectionChanged.connect(self._selected)
        self.clear_grid()

    def clear_grid(self, message: str = "Confirm the chords, then press Generate."):
        self.clear()
        self.line_ids = []
        self.mute_buttons, self.solo_buttons, self.lock_buttons = {}, {}, {}
        self.setRowCount(1)
        self.setColumnCount(1)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        item = QTableWidgetItem(message)
        item.setForeground(QBrush(QColor(MUTED)))
        self.setItem(0, 0, item)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)

    def _button(self, text, tip, line_id, signal, color, checked=False):
        b = QToolButton()
        b.setText(text)
        b.setCheckable(True)
        b.setChecked(checked)
        b.setToolTip(tip)
        b.setStyleSheet(f"QToolButton {{ padding: 0 4px; }} QToolButton:checked {{ background: {color}; color: #111; }}")
        b.toggled.connect(lambda on, lid=line_id: signal.emit(lid, on))
        return b

    def show_orchestration(self, orch, key: Key, name_style: str = "ableton", locked=frozenset()):
        insts = instruments()
        self.clear()
        self.horizontalHeader().show()
        self.verticalHeader().show()
        chords = orch.chords
        lines = [ln for ln in orch.lines if ln.id in locked or any(p is not None for p in orch.cells[ln.id])]
        self.line_ids = [ln.id for ln in lines]
        self.setRowCount(len(lines))
        self.setColumnCount(CTRL_COLS + len(chords))
        sources = orch.sources
        heads = ["L", "M", "S", "⠿"] + [c.label.symbol(key) + (f" · {src}" if src != orch.approach else "")
                                        for c, src in zip(chords, sources)]
        self.setHorizontalHeaderLabels(heads)
        for i in range(len(chords)):
            self.horizontalHeaderItem(CTRL_COLS + i).setToolTip(
                "Click for this chord's menu: regenerate it, or use another alternative's voicing"
                + (f" (now: alternative {sources[i]}'s voicing)" if sources[i] != orch.approach else ""))
        self.setVerticalHeaderLabels([("🔒 " if ln.id in locked else "") + ln.label for ln in lines])
        hh = self.horizontalHeader()
        for c in range(CTRL_COLS):
            hh.setSectionResizeMode(c, QHeaderView.Fixed)
            self.setColumnWidth(c, 30)
        self._lengths = [ch.end - ch.start for ch in chords]
        for i in range(len(chords)):
            hh.setSectionResizeMode(CTRL_COLS + i, QHeaderView.Interactive)
        self._fit_columns()
        errors = {(pid, i.chord) for i in orch.report.errors for pid in i.parts}
        notes_for: dict[tuple, list[str]] = {}
        for issue in orch.report.issues:
            for pid in issue.parts:
                notes_for.setdefault((pid, issue.chord), []).append(issue.message)
        warn = {(pid, i.chord) for i in orch.report.warnings for pid in i.parts}
        self.mute_buttons, self.solo_buttons, self.lock_buttons = {}, {}, {}
        for r, ln in enumerate(lines):
            inst = insts[ln.instrument]
            tint = QColor(SECTION_TINT[inst.section])
            lk = self._button("L", "Lock this part: Regenerate keeps its notes", ln.id, self.lock_toggled,
                              LOCK_COLOR, checked=ln.id in locked)
            m = self._button("M", "Mute this part", ln.id, self.mute_toggled, "#e0a040")
            s = self._button("S", "Solo this part", ln.id, self.solo_toggled, "#60c060")
            self.lock_buttons[ln.id], self.mute_buttons[ln.id], self.solo_buttons[ln.id] = lk, m, s
            self.setCellWidget(r, 0, lk)
            self.setCellWidget(r, 1, m)
            self.setCellWidget(r, 2, s)
            has_notes = bool(orch.part(ln.id).notes)
            handle = DragHandle(lambda lid=ln.id: self.files_for_part(lid),
                                tip=f"Drag {ln.label} into Ableton" if has_notes else "This part rests throughout")
            if not has_notes:
                handle.setEnabled(False)
            self.setCellWidget(r, 3, handle)
            cells = orch.cells[ln.id]
            for i, p in enumerate(cells):
                held = (i > 0 and p is not None and cells[i - 1] == p and chords[i - 1].label == chords[i].label
                        and chords[i - 1].end == chords[i].start)
                text = "–" if p is None else ("~ " if held else "") + note_name(p, name_style, key)
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                bg = RED_BG if (ln.id, i) in errors else (WARN_BG if (ln.id, i) in warn else None)
                item.setBackground(QBrush(QColor(bg) if bg else tint))
                if p is None:
                    item.setForeground(QBrush(QColor(MUTED)))
                elif not inst.is_comfortable(p):
                    item.setForeground(QBrush(QColor(YELLOW)))
                else:
                    item.setForeground(QBrush(QColor(TEXT)))
                tip = f"{ln.label}: " + ("rests" if p is None else note_name(p, name_style, key)
                                         + (" (held from the previous chord)" if held else ""))
                if p is not None:
                    regs = inst.register_notes(p)
                    if regs:
                        tip += f" · {regs[0]}"
                for msg in notes_for.get((ln.id, i), []):
                    tip += "\n" + msg
                item.setToolTip(tip)
                self.setItem(r, CTRL_COLS + i, item)

    def set_locked(self, line_id: str, on: bool, label: str):
        """Update a row's lock mark without rebuilding the grid."""
        if line_id in self.line_ids:
            r = self.line_ids.index(line_id)
            self.setVerticalHeaderItem(r, QTableWidgetItem(("🔒 " if on else "") + label))
            b = self.lock_buttons.get(line_id)
            if b is not None and b.isChecked() != on:
                b.blockSignals(True)
                b.setChecked(on)
                b.blockSignals(False)

    def _header_clicked(self, col: int):
        if col >= CTRL_COLS and self.line_ids:
            self.chord_menu_requested.emit(col - CTRL_COLS)

    def _context_menu(self, pos):
        idx = self.indexAt(pos)
        if not idx.isValid() or not self.line_ids or idx.row() >= len(self.line_ids):
            return
        col = idx.column() - CTRL_COLS
        self.part_menu_requested.emit(self.line_ids[idx.row()], col if col >= 0 else -1)

    def _fit_columns(self):
        """Chord columns share the free width in proportion to chord length (at least 58 px each)."""
        lengths = getattr(self, "_lengths", [])
        if not lengths or not self.line_ids:
            return
        free = self.viewport().width() - sum(self.columnWidth(c) for c in range(CTRL_COLS)) - 4
        per_tick = max(free / sum(lengths), 58 / min(lengths))
        for i, n in enumerate(lengths):
            self.setColumnWidth(CTRL_COLS + i, int(n * per_tick))

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        self._fit_columns()

    def _selected(self):
        rows = {i.row() for i in self.selectedIndexes()}
        if len(rows) == 1 and self.line_ids:
            r = rows.pop()
            if r < len(self.line_ids):
                self.part_selected.emit(self.line_ids[r])

    def select_part(self, line_id: str):
        if line_id in self.line_ids:
            self.selectRow(self.line_ids.index(line_id))


class PianoRoll(QWidget):
    """The selected part's whole line, with bar lines and chord boundaries."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(110)
        self.notes = []
        self.length = BAR
        self.chord_starts: list[int] = []
        self.title = ""
        self.name_style = "ableton"
        self.position: int | None = None

    def set_part(self, title: str, notes, length: int, chord_starts, name_style="ableton"):
        self.title, self.notes, self.length = title, list(notes), max(length, 1)
        self.chord_starts, self.name_style = list(chord_starts), name_style
        self.update()

    def clear_part(self):
        self.set_part("", [], BAR, [])

    def set_position(self, tick: int | None):
        self.position = tick
        self.update()

    def paintEvent(self, _):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1b1c1f"))
        w, h = self.width(), self.height()
        left, top, bottom = 44, 18, h - 6
        p.setPen(QColor(MUTED))
        if not self.notes:
            p.drawText(8, 14, self.title + ("  (rests throughout)" if self.title else
                                            "Select a part in the grid to see its line here."))
            return
        p.drawText(8, 14, self.title)
        lo = min(n.pitch for n in self.notes) - 2
        hi = max(n.pitch for n in self.notes) + 2
        span = max(hi - lo, 1)
        sx = (w - left - 8) / self.length

        def y(pitch):
            return top + (hi - pitch) / span * (bottom - top)

        p.drawText(4, int(y(hi - 2)) + 4, note_name(hi - 2, self.name_style))
        p.drawText(4, int(y(lo + 2)) + 4, note_name(lo + 2, self.name_style))
        for t in range(0, self.length + 1, BAR):
            p.setPen(QPen(QColor("#44464d"), 1))
            p.drawLine(int(left + t * sx), top, int(left + t * sx), bottom)
        for t in self.chord_starts:
            p.setPen(QPen(QColor("#33353b"), 1, Qt.DashLine))
            p.drawLine(int(left + t * sx), top, int(left + t * sx), bottom)
        nh = max(3.0, (bottom - top) / span)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#5b9bd5"))
        for n in self.notes:
            p.drawRoundedRect(QRectF(left + n.start * sx + 1, y(n.pitch) - nh / 2, max(2.0, n.length * sx - 2), nh),
                              2, 2)
        if self.position is not None:
            p.setPen(QPen(QColor("#e6e6e6"), 1))
            x = int(left + self.position * sx)
            p.drawLine(x, top, x, bottom)
