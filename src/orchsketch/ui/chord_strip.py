"""Chord strip: one clickable cell per chord segment (SPEC §6, item 2)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ..analysis.session import SegmentResult
from ..midi_io import BAR, PPQ
from ..theory import Key
from .theme import MUTED, PANEL, STATUS_COLORS

PX_PER_EIGHTH = 34
MIN_CELL = 78


def length_text(ticks: int) -> str:
    if ticks % BAR == 0:
        bars = ticks // BAR
        return f"{bars} bar" + ("s" if bars > 1 else "")
    beats = ticks / PPQ
    return f"{beats:g} beat" + ("" if beats == 1 else "s")


def position_short(tick: int) -> str:
    bar, beat = tick // BAR + 1, (tick % BAR) / PPQ + 1
    return f"{bar}.{beat:g}"


class ChordCell(QFrame):
    clicked = Signal(int)

    def __init__(self, result: SegmentResult, key: Key, selected: bool = False):
        super().__init__()
        self.index = result.segment.index
        seg = result.segment
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(max(MIN_CELL, seg.length // (PPQ // 2) * PX_PER_EIGHTH))
        self.setFixedHeight(96)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(1)

        if seg.is_rest:
            status, symbol, roman = None, "rest", ""
        elif result.label is None:
            status, symbol, roman = "unrecognized", "?", "set by hand"
        else:
            status = result.status
            symbol, roman = result.label.symbol(key), result.label.roman(key)

        pos = QLabel(position_short(seg.start) + ("   ped" if seg.pedal else ""))
        pos.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        sym = QLabel(symbol)
        sym.setStyleSheet("font-size: 17px; font-weight: 600;")
        rom = QLabel(roman)
        rom.setStyleSheet("font-size: 12px;")
        ln = QLabel(length_text(seg.length))
        ln.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        for w in (pos, sym, rom, ln):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(w)
        lay.addStretch(1)

        border = STATUS_COLORS.get(status, "#3a3c42")
        width = 3 if selected else (2 if status in ("confirmed", "corrected", "unrecognized") else 1)
        bg = "#3a2526" if status == "unrecognized" else ("#26282c" if seg.is_rest else PANEL)
        self.setObjectName("cell")
        self.setStyleSheet(
            f"#cell {{ background: {bg}; border: {width}px solid {border}; border-radius: 6px; }}"
        )
        tip = {"auto": "Best guess - click to confirm or change", "confirmed": "Confirmed",
               "corrected": "Corrected by you", "unrecognized": "Not recognized - click to set it"}
        self.setToolTip(tip.get(status, "No notes here"))

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming)
        # The click handler may rebuild the strip and delete this cell, so touch
        # nothing on `self` after emitting.
        if event.button() == Qt.LeftButton:
            event.accept()
            self.clicked.emit(self.index)
        else:
            super().mousePressEvent(event)


class ChordStrip(QScrollArea):
    cell_clicked = Signal(int)

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFixedHeight(126)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cells: list[ChordCell] = []
        self._empty()

    def _empty(self):
        w = QLabel("Drop a block-chord MIDI file here, or use Open chords…")
        w.setAlignment(Qt.AlignCenter)
        w.setStyleSheet(f"color: {MUTED}; font-size: 14px;")
        self.setWidget(w)
        self.cells = []

    def show_results(self, results: list[SegmentResult], key: Key, selected: int | None):
        if not results:
            self._empty()
            return
        host = QWidget()
        lay = QHBoxLayout(host)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        self.cells = []
        for r in results:
            cell = ChordCell(r, key, selected == r.segment.index)
            cell.clicked.connect(self.cell_clicked)
            lay.addWidget(cell)
            self.cells.append(cell)
        lay.addStretch(1)
        self.setWidget(host)
