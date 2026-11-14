"""Main window: load a chord clip, review/correct labels, generate, compare, edit, audition and export.

Milestone 4 added the three alternatives (tabs A/B/C, each with its one-line reason), locks and
regeneration (unlocked parts, one part, one chord), per-chord and per-bar swaps with a neighbour re-check,
undo/redo for every edit, the top-voice option, keep-as-is, the global sliders and presets.
Milestone 5 adds the melody and bass file slots, rhythm patterns (per section, per part), moderate mode
(Character slider), the independent bass, re-strike every bar, and per-section sliders (side panel scope).
Milestone 6 adds projects (File > New / Open / Save / Save As, a "*" in the title for unsaved changes, and
a save prompt before anything is thrown away) and the full export options (per-part files, the full-score
file or both, plus optional combined divisi files).
Milestone 7 (v1.2) adds the pattern engine controls: a note mode (Chord tones / Hybrid / Scale steps) and an
accent grouping per section, and pattern alternatives 1/2/3 on top of each harmony alternative (a second tab
row, Regenerate patterns; exported as A2, A3...).
Generation of the three alternatives runs in the background so the window stays responsive.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QCursor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QInputDialog,
    QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter, QTabBar,
    QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__
from ..analysis import AnalysisSession, ChordLabel, SymbolError, parse_symbol
from ..checker import chords_from_session
from ..edits import bar_chords, regenerate, regenerate_chord, regenerate_part, swap
from .. import project as pj
from ..export import BOTH, EXPORT_CHOICES, EXPORT_ROOT, FULL, PARTS, export_all, export_folder, export_part_files, safe_name
from .. import patterns as pat
from .. import pattern_alts as pa
from .. import shapes as shp
from .. import expression as ex
from ..generator import (
    APPROACH, APPROACHES, CHARACTERS, DENSITY_STEPS, DOUBLINGS, DYNAMIC_STEPS, FILL_NAMES, FILL_NONE, FILLS, FORCES,
    MELODY_HOSTS, TOP_INPUT, TOP_SMOOTH, Ensemble, GenerationError, Orchestration, Settings, generate_all, rerender,
)
from ..history import History
from ..instruments import SECTIONS, instruments
from ..midi_io import InputError, read_chord_file, read_monophonic_file, write_notes
from ..playback.player import Player
from ..playback.synth import SynthError
from ..presets import DEFAULT_PRESET, USER_PRESETS, Preset, find, load_all, preset_id, save_preset
from ..theory import MAJOR_TONICS, MINOR_TONICS, Key, note_name
from .chord_strip import ChordStrip, length_text
from .grid import DragHandle, PartGrid, PianoRoll
from .theme import MUTED

DOCS = Path.home() / "Documents" / "OrchSketch"
FORCE_NAMES = {"solo": "Solo", "section": "Section", "divisi": "Divisi"}
DENSITY_NAMES = {1: "1 · sparse", 2: "2", 3: "3", 4: "4", 5: "5 · full"}
CHARACTER_NAMES = {"safe": "Safe", "moderate": "Moderate"}
DOUBLING_NAMES = {"auto": "Doubling: auto", "off": "Doubling: off", "up": "Doubling: 8va", "down": "Doubling: 8vb"}
CUSTOM = "custom"
ALL = "all"
SLIDERS = ("character", "forces", "density", "dynamics")
RENDER_KEYS = ("dynamics", "pattern", "note_mode", "accent", "shape", "fill", "swell")  # apply at once, without regenerating
NO_PALTS = ((None, None, None),) * 3  # pattern alternatives per harmony tab: (None = pattern 1, 2, 3)
EXPORT_NAMES = {PARTS: "Per-part files", FULL: "Full score file", BOTH: "Parts + full score"}
SAVE, DISCARD, CANCEL = "save", "discard", "cancel"


def default_values() -> dict:
    return {sec: {"character": "safe", "forces": "section", "density": 5, "dynamics": "mf",
                  "pattern": pat.SUSTAIN, "note_mode": pat.CHORD_TONES, "accent": pat.PATTERN_ACCENTS,
                  "shape": shp.STEADY, "fill": FILL_NONE, "swell": ex.SWELL_OFF}
            for sec in SECTIONS}


# v1.4: window-wide expression options (Settings fields of the same name). EXPRESSION_OFF is v1.3 (the generator's
# defaults, and what a project saved before v1.4 opens with); a new project starts with EXPRESSION_DEFAULTS:
# Balance sections and long notes only in a high doubling on (Sam's ear tests T5/T7/X2/X3/X4).
EXPRESSION_OFF = {"curves": False, "phrase_arcs": False, "beat_accents": False, "balance": False,
                  "humanize": ex.HUMANIZE_OFF, "riser": 0, "riser_section": "strings", "shepard": False,
                  "long_doubling": False}
EXPRESSION_DEFAULTS = dict(EXPRESSION_OFF, balance=True, long_doubling=True)


def freeze(d: dict) -> tuple:
    return tuple(sorted((sec, k, v) for sec, vals in d.items() for k, v in vals.items()))


def thaw(t: tuple) -> dict:
    out = default_values()
    for sec, k, v in t:
        out[sec][k] = v
    return out


class DropButton(QPushButton):
    """A button that also takes a dropped .mid file (the melody and bass slots)."""
    file_dropped = Signal(str)

    def __init__(self, text: str):
        super().__init__(text)
        self.setAcceptDrops(True)

    @staticmethod
    def _midi(e) -> str | None:
        if e.mimeData().hasUrls():
            for u in e.mimeData().urls():
                if u.toLocalFile().lower().endswith((".mid", ".midi")):
                    return u.toLocalFile()
        return None

    def dragEnterEvent(self, e):  # noqa: N802
        if self._midi(e):
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        path = self._midi(e)
        if path:
            e.acceptProposedAction()
            self.file_dropped.emit(path)


@dataclass(frozen=True)
class EditState:
    """One undo step: everything you can edit (orchestrations are shared, never changed in place)."""
    labels: tuple = ()  # per segment: (correction or None, confirmed)
    tonic: str = "A"
    mode: str = "minor"
    preset: str = DEFAULT_PRESET
    active: frozenset = frozenset()
    values: tuple = ()  # per-section slider values and patterns (freeze())
    ipatterns: tuple = ()  # instrument patterns from the preset
    ppatterns: tuple = ()  # per-part patterns
    restrike: bool = False
    melody: tuple | None = None  # (file name, notes, file bytes)
    bass: tuple | None = None
    mel_inst: str | None = None
    mel_double: str = "auto"
    independent: bool = False
    top_voice: str = TOP_SMOOTH
    keep: bool = False
    seed: int = 1
    alts: tuple = (None, None, None)  # Orchestration, an error message (str) or None, for A, B, C
    locks: tuple = (frozenset(), frozenset(), frozenset())
    tab: int = 0
    dirty: bool = False  # generation settings changed since the last Generate
    palts: tuple = NO_PALTS  # per harmony tab: (None, pattern 2, pattern 3) Orchestration or None (not built)
    ptabs: tuple = (0, 0, 0)  # per harmony tab: the pattern alternative shown (0 = pattern 1)
    phrase: int = 4  # v1.3: bars per phrase (shapes, fills)
    emphasis: bool = False  # v1.3: pattern emphasis
    clear_low: bool = False  # v1.3: clear low register
    change_accents: bool = False  # v1.3: accent chord changes
    theme: bool = False  # v1.3: unison/octave theme (a generation setting)
    expression: tuple = ()  # v1.4: every expression option, (key, value) pairs; () = a v1.3 project (all off)
    extra: dict = field(default_factory=dict, compare=False, hash=False)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"OrchSketch {__version__}")
        self.resize(1360, 860)
        self.setAcceptDrops(True)
        self.settings = QSettings("OrchSketch", "OrchSketch")
        self.name_style = self.settings.value("note_names", "ableton")
        self.session: AnalysisSession | None = None
        self.selected: int | None = None
        self.alts: list = [None, None, None]
        self.locks: list[frozenset] = [frozenset(), frozenset(), frozenset()]
        self.tab = 0
        self.palts: list[list] = [[None, None, None] for _ in range(3)]  # per harmony tab: patterns 2 and 3
        self.ptabs: list[int] = [0, 0, 0]  # per harmony tab: pattern alternative shown (0 = pattern 1)
        self.dirty = False
        self.player: Player | None = None
        self.player_factory = Player  # tests replace this with a silent backend
        self.muted: set[str] = set()
        self.soloed: set[str] = set()
        self.export_root = EXPORT_ROOT
        self.presets_folder = USER_PRESETS
        self.presets, problems = load_all(self.presets_folder)
        self.active: frozenset[str] = frozenset(find(self.presets, DEFAULT_PRESET).instruments)
        self.values = default_values()  # per-section sliders and patterns
        self.ipatterns: dict[str, str] = {}  # instrument -> pattern (presets)
        self.ppatterns: dict[str, str] = {}  # line id -> pattern (part menu)
        self.scope = ALL
        self.melody_file: tuple | None = None  # (file name, notes, file bytes)
        self.bass_file: tuple | None = None
        self.chords_file: tuple | None = None  # (file name, file bytes) of the chord clip
        self.project_path: Path | None = None
        self.projects_root = pj.PROJECTS_ROOT
        self._saved = None  # the history state that was last saved or opened (None: never)
        self._saved_tempo = 140
        self.history = History()
        self._restoring = False
        self.run_async = True  # tests set False: Generate then runs in the calling thread
        self.parallel = True  # A, B and C in worker processes (parallel.py); False: one process
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._job = None
        self._build()
        self.playhead = QTimer(self)
        self.playhead.setInterval(50)
        self.playhead.timeout.connect(self._update_playhead)
        self.job_timer = QTimer(self)
        self.job_timer.setInterval(40)
        self.job_timer.timeout.connect(self._poll_job)
        self.history.reset(self.snapshot())
        self._mark_saved()
        if problems:
            QTimer.singleShot(0, lambda: self.statusBar().showMessage(
                "Some saved presets couldn't be read: " + "; ".join(problems), 15000))

    # ------------------------------------------------------------------ layout
    def _build(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)

        bar = QHBoxLayout()
        self.open_btn = QPushButton("Open…")
        self.open_btn.setToolTip("Open a block-chord MIDI file or an OrchSketch project (.osk)")
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
        self.undo_btn = QToolButton()
        self.undo_btn.setText("↶ Undo")
        self.undo_btn.clicked.connect(self.undo)
        self.redo_btn = QToolButton()
        self.redo_btn.setText("↷ Redo")
        self.redo_btn.clicked.connect(self.redo)
        for w in (self.open_btn, self.file_label):
            bar.addWidget(w)
        bar.addSpacing(12)
        self.slot_btn, self.slot_label, self.slot_clear = {}, {}, {}
        for kind, text in (("melody", "Melody…"), ("bass", "Bass…")):
            b = DropButton(text)
            b.setToolTip(f"Open or drop a monophonic {kind} clip (same start as the chords). "
                         + ("It goes to one instrument, and the harmony is voiced around it." if kind == "melody"
                            else "The low strings, low brass and low winds double it in octaves."))
            b.clicked.connect(lambda _=False, k=kind: self.open_part_dialog(k))
            b.file_dropped.connect(lambda path, k=kind: self.load_part_file(k, path))
            lab = QLabel("none")
            lab.setStyleSheet(f"color: {MUTED};")
            x = QToolButton()
            x.setText("×")
            x.setToolTip(f"Remove the {kind} file")
            x.clicked.connect(lambda _=False, k=kind: self.clear_part_file(k))
            x.setEnabled(False)
            self.slot_btn[kind], self.slot_label[kind], self.slot_clear[kind] = b, lab, x
            for w in (b, lab, x):
                bar.addWidget(w)
            bar.addSpacing(6)
        bar.addStretch(1)
        for label, w in (("Key", self.tonic), (None, self.mode), ("Tempo", self.tempo)):
            if label:
                bar.addWidget(QLabel(label))
            bar.addWidget(w)
        bar.addSpacing(16)
        bar.addWidget(self.confirm_btn)
        bar.addSpacing(16)
        bar.addWidget(self.undo_btn)
        bar.addWidget(self.redo_btn)
        root.addLayout(bar)

        gen = QHBoxLayout()
        self.preset_box = QComboBox()
        self.preset_box.setToolTip("Ensemble preset: sets the instruments and the slider starting points")
        self._fill_presets(DEFAULT_PRESET)
        self.preset_box.activated.connect(self._preset_chosen)
        self.parts_btn = QPushButton("Parts…")
        self.parts_btn.setToolTip("Turn single instruments on or off")
        self.parts_btn.clicked.connect(lambda: self.show_menu(self.build_parts_menu()))
        self.save_preset_btn = QPushButton("Save preset…")
        self.save_preset_btn.setToolTip(f"Save the instruments and sliders as your own preset ({USER_PRESETS})")
        self.save_preset_btn.clicked.connect(self.save_preset_dialog)
        self.top_box = QComboBox()
        self.top_box.addItem("Top voice: smooth", TOP_SMOOTH)
        self.top_box.addItem("Top voice: follow input", TOP_INPUT)
        self.top_box.setToolTip("Smooth: the top voice moves by the smallest step.\n"
                                "Follow input: the top voice takes your clip's top note (nearest octave).")
        self.top_box.currentIndexChanged.connect(lambda _: self._setting_changed("Top voice"))
        self.keep_box = QCheckBox("Keep my voicing (strings)")
        self.keep_box.setToolTip("Your input voicing is kept exactly as written, spread over the string lines "
                                 "low to high; everything else is orchestrated around it.")
        self.keep_box.toggled.connect(lambda _: self._setting_changed("Keep as-is"))
        self.mel_inst_box = QComboBox()
        self.mel_inst_box.setToolTip("Which instrument plays your melody (auto: chosen by register for each "
                                     "alternative - A horns, B Violins I, C flute - with fallbacks)")
        self.mel_inst_box.activated.connect(lambda _: self._setting_changed("Melody instrument"))
        self.mel_double_box = QComboBox()
        for d in DOUBLINGS:
            self.mel_double_box.addItem(DOUBLING_NAMES[d], d)
        self.mel_double_box.setToolTip("Melody octave doubling. Auto doubles at Density 4-5 "
                                       "(A an octave down, B and C an octave up).")
        self.mel_double_box.activated.connect(lambda _: self._setting_changed("Melody doubling"))
        self.indep_box = QCheckBox("Independent bass")
        self.indep_box.setToolTip("Moderate mode only: the bass moves by step toward the next chord's bass "
                                  "instead of holding the chord's bass note. Needs Character at Moderate for "
                                  "the sections playing the bass, and no bass file.")
        self.indep_box.toggled.connect(lambda _: self._setting_changed("Independent bass"))
        self.theme_box = QCheckBox("Theme in octaves")
        self.theme_box.setToolTip("Unison/octave theme: your melody (or, without a melody file, your clip's top "
                                  "note) in octaves across horns, trombones, cellos and choir instead of voiced; "
                                  "the rest of the orchestra harmonizes around it. Takes effect at the next "
                                  "Generate.")
        self.theme_box.toggled.connect(lambda on: self._setting_changed("Theme in octaves" if on else "Theme off"))
        self.restrike_box = QCheckBox("Re-strike every bar")
        self.restrike_box.setToolTip("Sustain: re-strike held notes at every bar line instead of tying them over "
                                     "repeated chords. Applies at once.")
        self.restrike_box.toggled.connect(self._restrike_toggled)
        self.seed = QSpinBox()
        self.seed.setRange(1, 9999)
        self.seed.setValue(1)
        self.seed.setToolTip("Same chords, settings and seed always give the same result")
        self.seed.valueChanged.connect(lambda _: self._setting_changed("Seed"))
        self.generate_btn = QPushButton("Generate")
        self.generate_btn.clicked.connect(self.generate)
        gen.addWidget(QLabel("Preset"))
        for w in (self.preset_box, self.parts_btn, self.save_preset_btn):
            gen.addWidget(w)
        gen.addSpacing(16)
        gen.addWidget(self.top_box)
        gen.addWidget(self.keep_box)
        gen.addSpacing(12)
        for w in (self.mel_inst_box, self.mel_double_box, self.theme_box, self.indep_box, self.restrike_box):
            gen.addWidget(w)
        gen.addStretch(1)
        gen.addWidget(QLabel("Seed"))
        gen.addWidget(self.seed)
        gen.addWidget(self.generate_btn)
        root.addLayout(gen)

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

        tabs = QHBoxLayout()
        self.tabs = QTabBar()
        for a in APPROACHES:
            self.tabs.addTab(f"{a} · {APPROACH[a].name}")
        self.tabs.currentChanged.connect(self.set_tab)
        self.regen_btn = QPushButton("Regenerate unlocked")
        self.regen_btn.setToolTip("A new variation of this alternative; locked parts keep their notes")
        self.regen_btn.clicked.connect(self.regenerate_unlocked)
        self.reason_label = QLabel("")
        self.reason_label.setStyleSheet(f"color: {MUTED};")
        self.reason_label.setWordWrap(True)
        self.pattern_tabs = QTabBar()
        for k in pa.PATTERN_ALTS:
            self.pattern_tabs.addTab(f"Patterns {k}")
        self.pattern_tabs.setToolTip("Pattern alternatives on top of this harmony. 1 is exactly your pattern "
                                     "settings; 2 and 3 pick other patterns and accents from the same families "
                                     "(the notes at every chord change stay the same).")
        self.pattern_tabs.currentChanged.connect(self.set_pattern_tab)
        self.regen_patterns_btn = QPushButton("Regenerate patterns")
        self.regen_patterns_btn.setToolTip("New pattern choices for this pattern alternative (2 or 3); locked "
                                           "parts keep theirs")
        self.regen_patterns_btn.clicked.connect(self.regenerate_patterns_action)
        tabs.addWidget(self.tabs)
        tabs.addWidget(self.regen_btn)
        tabs.addSpacing(12)
        tabs.addWidget(self.pattern_tabs)
        tabs.addWidget(self.regen_patterns_btn)
        tabs.addSpacing(12)
        tabs.addWidget(self.reason_label, 1)
        root.addLayout(tabs)

        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.grid = PartGrid(self.files_for_part)
        self.grid.part_selected.connect(self.show_part)
        self.grid.mute_toggled.connect(self.set_mute)
        self.grid.solo_toggled.connect(self.set_solo)
        self.grid.lock_toggled.connect(self.set_lock)
        self.grid.chord_menu_requested.connect(lambda i: self.show_menu(self.build_column_menu(i)))
        self.grid.part_menu_requested.connect(lambda lid, i: self.show_menu(self.build_part_menu(lid, i)))
        self.piano = PianoRoll()
        split = QSplitter(Qt.Vertical)
        split.addWidget(self.grid)
        split.addWidget(self.piano)
        split.addWidget(self.details)
        split.setSizes([430, 120, 90])
        middle = QHBoxLayout()
        middle.addWidget(split, 1)
        panel = QScrollArea()  # the side panel scrolls on small screens instead of squeezing its rows
        panel.setWidget(self._slider_panel())
        panel.setWidgetResizable(True)
        panel.setFrameShape(QFrame.NoFrame)
        panel.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        panel.setMaximumWidth(300)
        panel.setMinimumWidth(300)
        middle.addWidget(panel)
        root.addLayout(middle, 1)

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
        self.export_box = QComboBox()
        for k in EXPORT_CHOICES:
            self.export_box.addItem(EXPORT_NAMES[k], k)
        self.export_box.setToolTip("What Export and the All handle give you: one file per part, one multi-track "
                                   "full-score file, or both")
        choice = self.settings.value("export_choice", BOTH)
        self.export_box.setCurrentIndex(max(0, self.export_box.findData(choice)))
        self.export_box.currentIndexChanged.connect(
            lambda _: self.settings.setValue("export_choice", self.export_box.currentData()))
        self.combined_box = QCheckBox("Combined divisi")
        self.combined_box.setToolTip("Also write one file per instrument with all its lines (divisi, a2, horns "
                                     "1-4), e.g. Hn-all")
        self.combined_box.setChecked(str(self.settings.value("export_combined", "false")).lower() == "true")
        self.combined_box.toggled.connect(lambda on: self.settings.setValue("export_combined", bool(on)))
        self.export_parts_btn = QPushButton("Export")
        self.export_parts_btn.setToolTip("Save the MIDI files to Documents\\OrchSketch\\Exports\\{project}")
        self.export_parts_btn.clicked.connect(self.export_parts_action)
        tr.addWidget(self.all_handle)
        tr.addWidget(self.export_box)
        tr.addWidget(self.combined_box)
        tr.addWidget(self.export_parts_btn)
        root.addLayout(tr)
        self.checker_label = QLabel("")
        info = QHBoxLayout()
        info.addWidget(self.checker_label, 1)
        root.addLayout(info)
        self.setCentralWidget(central)
        self.status_label = QLabel("")
        self.statusBar().addWidget(self.status_label, 1)
        self._menus()
        self._apply_preset_values(find(self.presets, DEFAULT_PRESET))
        self._show_slots()
        self._refresh()

    def _slider_panel(self) -> QWidget:
        box = QGroupBox("Sliders")
        box.setToolTip("Sliders for all sections at once, or for one section (SPEC §6)")
        form = QFormLayout(box)
        self.scope_box = QComboBox()
        self.scope_box.addItem("All sections", ALL)
        for sec in SECTIONS:
            self.scope_box.addItem(sec.capitalize(), sec)
        self.scope_box.setToolTip("All sections: the master sliders move every section. Pick a section to set "
                                  "its own values.")
        self.scope_box.currentIndexChanged.connect(lambda _: self.set_scope(self.scope_box.currentData()))
        form.addRow("Set", self.scope_box)

        def slider(n, tip):
            s = QSlider(Qt.Horizontal)
            s.setRange(0, n - 1)
            s.setPageStep(1)
            s.setTickPosition(QSlider.TicksBelow)
            s.setTickInterval(1)
            s.setToolTip(tip)
            s.setMinimumWidth(150)
            return s

        self.character = slider(len(CHARACTERS), "Character: Safe uses chord tones only. Moderate adds 9ths, "
                                                 "sus and 6th colour in upper voices, passing tones in 8th/16th "
                                                 "patterns, playable range (flagged yellow) and the independent bass.")
        self.character_label = QLabel("Safe")
        self.forces = slider(len(FORCES), "Forces: solo players, full sections, or sections with divisi splits")
        self.forces_label = QLabel("")
        self.density = slider(len(DENSITY_STEPS), "Density: how many of the preset's parts play, "
                                                  "and how many doublings")
        self.density_label = QLabel("")
        self.dynamics = slider(len(DYNAMIC_STEPS), "Dynamics: velocity and CC1 (pp 30 … ff 120). "
                                                   "Applies at once, without regenerating.")
        self.dynamics_label = QLabel("")
        for name, s, lab in (("Character", self.character, self.character_label),
                             ("Forces", self.forces, self.forces_label),
                             ("Density", self.density, self.density_label),
                             ("Dynamics", self.dynamics, self.dynamics_label)):
            row = QVBoxLayout()
            row.addWidget(s)
            lab.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
            row.addWidget(lab)
            w = QWidget()
            w.setLayout(row)
            form.addRow(name, w)
        self.pattern_box = QComboBox()
        for pt in pat.PATTERNS:
            self.pattern_box.addItem(pat.PATTERN_NAMES[pt], pt)
        self.pattern_box.setToolTip("Rhythm pattern for these sections (choirs sing Sustain, 8ths, stabs or "
                                    "half-time). Right-click a part to give it its own. Applies at once.")
        self.pattern_label = QLabel("")
        self.pattern_label.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        self.pattern_label.setWordWrap(True)
        self.pattern_label.setMinimumHeight(30)
        prow = QVBoxLayout()
        prow.addWidget(self.pattern_box)
        prow.addWidget(self.pattern_label)
        pw = QWidget()
        pw.setLayout(prow)
        form.addRow("Pattern", pw)
        self.note_mode_box = QComboBox()
        for m in pat.NOTE_MODES:
            self.note_mode_box.addItem(pat.NOTE_MODE_NAMES[m], m)
        self.note_mode_box.setToolTip("How a shaped pattern moves (e.g. 8ths rising 1-2-3-2): Chord tones (every "
                                      "note a chord tone), Hybrid (beats on chord tones, notes in between on the "
                                      "scale) or Scale steps (the whole shape on the scale). Applies at once.")
        form.addRow("Note mode", self.note_mode_box)
        self.accent_box = QComboBox()
        for a in pat.ACCENTS:
            self.accent_box.addItem(pat.ACCENT_NAMES[a], a)
        self.accent_box.setToolTip("Accent grouping for 8th and 16th patterns: the first note of each group is "
                                   "accented; 'short' also shortens the others. Applies at once.")
        form.addRow("Accents", self.accent_box)
        self.shape_box = QComboBox()
        for sh in shp.SHAPES:
            self.shape_box.addItem(shp.SHAPE_NAMES[sh], sh)
        self.shape_box.setToolTip("Intensity shape: density, forces, pattern and dynamics change bar by bar. Your "
                                  "settings are the peak. " + " ".join(f"{shp.SHAPE_NAMES[k]}: {v.description}"
                                                                      for k, v in shp.library().items()
                                                                      if k != shp.STEADY)[:900]
                                  + " Applies at once.")
        form.addRow("Shape", self.shape_box)
        self.fill_box = QComboBox()
        for f in FILLS:
            self.fill_box.addItem(FILL_NAMES[f], f)
        self.fill_box.setToolTip("Phrase-end fill before every new phrase: a 16th run or a pickup in the "
                                 "section's top line into the next chord, or a drop-out on the last beat. "
                                 "Applies at once.")
        form.addRow("Fill", self.fill_box)
        self.phrase_box = QComboBox()
        for n in shp.PHRASES:
            self.phrase_box.addItem(f"{n} bars", n)
        self.phrase_box.setCurrentIndex(self.phrase_box.findData(4))
        self.phrase_box.setToolTip("Phrase length (all sections): where fills go and how the 4-bar phrase shape "
                                   "repeats. Applies at once.")
        form.addRow("Phrase", self.phrase_box)
        self.emphasis_box = QCheckBox("Pattern emphasis")
        self.emphasis_box.setToolTip("Patterned parts a dynamic step louder (unaccented notes at 90%), sustained "
                                     "parts under them a step softer, so the rhythm is heard. Applies at once.")
        self.clear_low_box = QCheckBox("Clear low register")
        self.clear_low_box.setToolTip("8th and 16th patterns below C3 play one level simpler (16ths become 8ths, "
                                      "8ths half-time), so the low register doesn't blur the rhythm. "
                                      "Applies at once.")
        self.change_accent_box = QCheckBox("Accent chord changes")
        self.change_accent_box.setToolTip("Every part's first note at a chord change a dynamic step louder. "
                                          "Applies at once.")
        ebox = QVBoxLayout()
        for w in (self.emphasis_box, self.clear_low_box, self.change_accent_box):
            ebox.addWidget(w)
            w.toggled.connect(lambda on, w=w: self._extra_toggled(w.text(), on))
        ew = QWidget()
        ew.setLayout(ebox)
        form.addRow("Rhythm", ew)
        self._build_expression(form)
        self.phrase_box.activated.connect(lambda _: self._extra_toggled(f"Phrase {self.phrase_box.currentData()} bars",
                                                                        True))
        self.shape_box.activated.connect(lambda _: self._slider_moved("shape", self.shape_box.currentData()))
        self.fill_box.activated.connect(lambda _: self._slider_moved("fill", self.fill_box.currentData()))
        self.mode_label = QLabel("")
        self.mode_label.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        self.mode_label.setWordWrap(True)
        form.addRow(self.mode_label)
        self.note_mode_box.activated.connect(
            lambda _: self._slider_moved("note_mode", self.note_mode_box.currentData()))
        self.accent_box.activated.connect(lambda _: self._slider_moved("accent", self.accent_box.currentData()))
        self.character.valueChanged.connect(lambda v: self._slider_moved("character", CHARACTERS[v]))
        self.forces.valueChanged.connect(lambda v: self._slider_moved("forces", FORCES[v]))
        self.density.valueChanged.connect(lambda v: self._slider_moved("density", DENSITY_STEPS[v]))
        self.dynamics.valueChanged.connect(lambda v: self._slider_moved("dynamics", DYNAMIC_STEPS[v]))
        self.pattern_box.activated.connect(lambda _: self._slider_moved("pattern", self.pattern_box.currentData()))
        note = QLabel("Character, Forces and Density take effect at the\nnext Generate. Everything below "
                      "Dynamics\napplies at once.")
        note.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
        form.addRow(note)
        box.setMaximumWidth(290)
        return box

    def _menus(self):
        m = self.menuBar().addMenu("&File")
        for text, slot, sc in (("&New project", self.new_project, QKeySequence.New),
                               ("&Open chords or project…", self.open_dialog, QKeySequence.Open),
                               ("&Save project", self.save_project, QKeySequence.Save),
                               ("Save project &as…", self.save_project_as, QKeySequence("Ctrl+Shift+S")),
                               (None, None, None),
                               ("&Generate", self.generate, QKeySequence("Ctrl+G")),
                               ("&Export", self.export_parts_action, QKeySequence("Ctrl+E")),
                               ("&Re-export input clip…", self.export_dialog, QKeySequence("Ctrl+Shift+E")),
                               ("&Quit", self.close, QKeySequence.Quit)):
            if text is None:
                m.addSeparator()
                continue
            a = QAction(text, self)
            a.setShortcut(sc)
            a.triggered.connect(slot)
            m.addAction(a)
        e = self.menuBar().addMenu("&Edit")
        self.undo_action = QAction("&Undo", self)
        self.undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self.undo_action.triggered.connect(self.undo)
        self.redo_action = QAction("&Redo", self)
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        self.redo_action.triggered.connect(self.redo)
        regen = QAction("Re&generate unlocked parts", self)
        regen.setShortcut(QKeySequence("Ctrl+R"))
        regen.triggered.connect(self.regenerate_unlocked)
        for a in (self.undo_action, self.redo_action, regen):
            e.addAction(a)
        v = self.menuBar().addMenu("&View")
        group = QActionGroup(self)
        for style, text in (("ableton", "Ableton note names (middle C = C3)"),
                            ("scientific", "Scientific note names (middle C = C4)")):
            a = QAction(text, self, checkable=True)
            a.setChecked(self.name_style == style)
            a.triggered.connect(lambda _=False, s=style: self.set_name_style(s))
            group.addAction(a)
            v.addAction(a)
        for i, a in enumerate(APPROACHES):
            act = QAction(f"Alternative {a}", self)
            act.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            act.triggered.connect(lambda _=False, k=i: self.tabs.setCurrentIndex(k))
            v.addAction(act)
        h = self.menuBar().addMenu("&Help")
        a = QAction("&About", self)
        a.triggered.connect(lambda: QMessageBox.about(
            self, "OrchSketch", f"OrchSketch {__version__}\nOrchestral sketching assistant (v1)."))
        h.addAction(a)

    def _fill_tonics(self, current: str):
        tonics = MINOR_TONICS if self.mode.currentText() == "minor" else MAJOR_TONICS
        self.tonic.blockSignals(True)
        self.tonic.clear()
        self.tonic.addItems(list(tonics))
        idx = self.tonic.findText(current)
        self.tonic.setCurrentIndex(idx if idx >= 0 else 0)
        self.tonic.blockSignals(False)

    def _fill_presets(self, current: str):
        self.preset_box.blockSignals(True)
        self.preset_box.clear()
        for p in self.presets:
            self.preset_box.addItem(p.name + ("" if p.builtin else "  (yours)"), p.id)
        self.preset_box.addItem("Custom", CUSTOM)
        idx = self.preset_box.findData(current)
        self.preset_box.setCurrentIndex(idx if idx >= 0 else self.preset_box.count() - 1)
        self.preset_box.blockSignals(False)

    # ------------------------------------------------------------------ current alternative
    @property
    def harmony(self) -> Orchestration | None:
        """The current harmony alternative (pattern 1): what harmony edits work on."""
        o = self.alts[self.tab]
        return o if isinstance(o, Orchestration) else None

    @property
    def orch(self) -> Orchestration | None:
        """What is shown, played and exported: the harmony alternative with the chosen pattern alternative."""
        h = self.harmony
        if h is None:
            return None
        k = self.ptabs[self.tab]
        p = self.palts[self.tab][k] if k else None
        return p if isinstance(p, Orchestration) else h

    def _ensure_pattern_alt(self, tab: int | None = None):
        """Build the shown pattern alternative of a tab if it isn't built yet (pattern 2/3, variation 0)."""
        tab = self.tab if tab is None else tab
        h, k = self.alts[tab], self.ptabs[tab]
        if k and isinstance(h, Orchestration) and self.palts[tab][k] is None:
            row = list(self.palts[tab])
            row[k] = pa.pattern_alternative(h, k + 1)
            self.palts[tab] = row

    @property
    def approach(self) -> str:
        return APPROACHES[self.tab]

    def _build_expression(self, form):
        """v1.4 Expression: Swell per section (the Set box), the rest for all sections. All apply at once."""
        head = QLabel("Expression")
        head.setStyleSheet("font-weight: bold; padding-top: 6px;")
        form.addRow(head)
        self.swell_box = QComboBox()
        for sw in ex.SWELLS:
            self.swell_box.addItem(ex.SWELL_NAMES[sw], sw)
        self.swell_box.setToolTip("CC1 dips and swells into every chord change, or only into the downbeat of each "
                                  "new phrase (turns CC curves on for these sections). Applies at once.")
        self.swell_box.activated.connect(lambda _: self._slider_moved("swell", self.swell_box.currentData()))
        form.addRow("Swell", self.swell_box)
        self.curves_box = QCheckBox("CC1/CC11 curves")
        self.curves_box.setToolTip("Export CC1 (dynamics) and CC11 (expression) curves per part instead of one "
                                   "CC1 value: they follow the shape, swell a little in held chords, and arc over "
                                   "each phrase (CC11 for winds and brass). The audition plays them as expression.")
        self.arcs_box = QCheckBox("Phrase arcs (velocity)")
        self.arcs_box.setToolTip("Velocities rise toward the middle of every phrase and fall back.")
        self.beats_box = QCheckBox("Beat accents (velocity)")
        self.beats_box.setToolTip("Beat 1 strongest, then beat 3; beats 2 and 4 and the off-beats a little softer.")
        self.balance_box = QCheckBox("Balance sections")
        self.balance_box.setToolTip("Woodwinds a dynamic step under the other sections at the same Dynamics "
                                    "(velocity and CC1), so they don't cover the strings.")
        self.long_dbl_box = QCheckBox("High doubling: long notes only")
        self.long_dbl_box.setToolTip("A melody doubling at C6 (Ableton C5) or above doubles only notes of a quarter "
                                     "or longer, so quick notes don't chatter in the piccolo or flute.")
        self.balance_box.setChecked(EXPRESSION_DEFAULTS["balance"])
        self.long_dbl_box.setChecked(EXPRESSION_DEFAULTS["long_doubling"])
        xbox = QVBoxLayout()
        for key, w in (("curves", self.curves_box), ("phrase_arcs", self.arcs_box), ("beat_accents", self.beats_box),
                       ("balance", self.balance_box), ("long_doubling", self.long_dbl_box)):
            xbox.addWidget(w)
            w.toggled.connect(lambda on, w=w: self._extra_toggled(w.text(), on))
        xw = QWidget()
        xw.setLayout(xbox)
        form.addRow("", xw)
        self.humanize_box = QComboBox()
        for h in ex.HUMANIZE:
            self.humanize_box.addItem(ex.HUMANIZE_NAMES[h], h)
        self.humanize_box.setToolTip("Seeded timing and velocity offsets in the export and the audition (the grid "
                                     "stays on the grid; the same offsets every time).")
        form.addRow("Humanize", self.humanize_box)
        self.riser_box = QComboBox()
        for b in ex.RISER_BARS:
            self.riser_box.addItem("Off" if not b else f"{b} bar" + ("s" if b > 1 else ""), b)
        self.riser_section_box = QComboBox()
        for sec in ex.RISER_SECTIONS:
            self.riser_section_box.addItem(sec.capitalize(), sec)
        self.shepard_box = QCheckBox("Shepard")
        self.shepard_box.setToolTip("Three layers rising together, the top fading out and the bottom fading in "
                                    "(CC11), each exported as its own riser part.")
        self.riser_box.setToolTip("A line rising by scale steps into the shape's hit (Build and hit), else into the "
                                  "last chord, landing on a chord tone. Exported as its own part (e.g. Vln1-rise).")
        rrow = QHBoxLayout()
        for w in (self.riser_box, self.riser_section_box, self.shepard_box):
            rrow.addWidget(w)
        rw = QWidget()
        rw.setLayout(rrow)
        form.addRow("Riser", rw)
        self.shepard_box.toggled.connect(lambda on: self._extra_toggled("Shepard riser", on))
        self.humanize_box.activated.connect(
            lambda _: self._extra_toggled(f"Humanize {self.humanize_box.currentText()}", True))
        self.riser_box.activated.connect(lambda _: self._extra_toggled(f"Riser {self.riser_box.currentText()}", True))
        self.riser_section_box.activated.connect(
            lambda _: self._extra_toggled(f"Riser in the {self.riser_section_box.currentData()}", True))

    def expression_values(self) -> dict:
        """The window-wide expression options (Settings fields)."""
        return {"curves": self.curves_box.isChecked(), "phrase_arcs": self.arcs_box.isChecked(),
                "beat_accents": self.beats_box.isChecked(), "balance": self.balance_box.isChecked(),
                "humanize": self.humanize_box.currentData() or ex.HUMANIZE_OFF,
                "riser": self.riser_box.currentData() or 0,
                "riser_section": self.riser_section_box.currentData() or "strings",
                "shepard": self.shepard_box.isChecked(), "long_doubling": self.long_dbl_box.isChecked()}

    def _expression_state(self) -> tuple:
        return tuple(sorted(self.expression_values().items()))

    def _show_expression(self, pairs: tuple):
        vals = dict(EXPRESSION_OFF, **dict(pairs))  # () = a project saved before v1.4: everything off
        for key, box in (("curves", self.curves_box), ("phrase_arcs", self.arcs_box),
                         ("beat_accents", self.beats_box), ("balance", self.balance_box),
                         ("shepard", self.shepard_box), ("long_doubling", self.long_dbl_box)):
            box.setChecked(bool(vals[key]))
        for key, box in (("humanize", self.humanize_box), ("riser", self.riser_box),
                         ("riser_section", self.riser_section_box)):
            box.setCurrentIndex(max(0, box.findData(vals[key])))

    def _expression_widgets(self) -> tuple:
        return (self.swell_box, self.curves_box, self.arcs_box, self.beats_box, self.balance_box, self.long_dbl_box,
                self.humanize_box, self.riser_box, self.riser_section_box, self.shepard_box)

    def _master_and_overrides(self, key: str):
        """The master value (all sections equal) and per-section overrides (only when they differ)."""
        vals = {sec: self.values[sec][key] for sec in SECTIONS}
        if len(set(vals.values())) == 1:
            return next(iter(vals.values())), ()
        common = max(set(vals.values()), key=lambda v: (list(vals.values()).count(v), str(v)))
        return common, tuple((sec, v) for sec, v in vals.items() if v != common)

    def render_settings(self) -> dict:
        """Settings fields that apply at once (no regeneration): dynamics, patterns, re-strike."""
        dyn, sdyn = self._master_and_overrides("dynamics")
        ptn, sptn = self._master_and_overrides("pattern")
        nm, snm = self._master_and_overrides("note_mode")
        acc, sacc = self._master_and_overrides("accent")
        shape, sshape = self._master_and_overrides("shape")
        fill, sfill = self._master_and_overrides("fill")
        swell, sswell = self._master_and_overrides("swell")
        return dict(swell=swell, section_swells=sswell, **self.expression_values(),dynamics=dyn, section_dynamics=sdyn, pattern=ptn, section_patterns=sptn,
                    note_mode=nm, section_note_modes=snm, accent=acc, section_accents=sacc,
                    instrument_patterns=tuple(sorted(self.ipatterns.items())),
                    part_patterns=tuple(sorted(self.ppatterns.items())), restrike_bars=self.restrike_box.isChecked(),
                    shape=shape, section_shapes=sshape, fill=fill, section_fills=sfill,
                    phrase=self.phrase_box.currentData() or 4, pattern_emphasis=self.emphasis_box.isChecked(),
                    clear_low=self.clear_low_box.isChecked(), change_accents=self.change_accent_box.isChecked())

    def gen_settings(self) -> Settings:
        forces, sforces = self._master_and_overrides("forces")
        density, sdensity = self._master_and_overrides("density")
        character, schar = self._master_and_overrides("character")
        ens = Ensemble(instruments=self.active, forces=forces, density=density, section_forces=sforces,
                       section_density=sdensity)
        tops: tuple = ()
        keep = None
        if self.session is not None:
            voicings = [tuple(sorted(r.segment.pitches)) for r in self.session.chord_results]
            tops = tuple(max(v) if v else None for v in voicings)
            if self.keep_box.isChecked():
                keep = tuple(voicings)
        return Settings(ens, self.top_box.currentData(), tops, keep, character=character, section_character=schar,
                        melody=self.melody_file[1] if self.melody_file else None,
                        bass=self.bass_file[1] if self.bass_file else None,
                        melody_instrument=self.mel_inst_box.currentData(),
                        melody_double=self.mel_double_box.currentData() or "auto",
                        independent_bass=self.indep_box.isChecked() and self.bass_file is None,
                        theme=self.theme_box.isChecked(), **self.render_settings())

    # ------------------------------------------------------------------ undo / redo
    def snapshot(self) -> EditState:
        labels = tuple((r.correction, r.confirmed) for r in self.session.results) if self.session else ()
        return EditState(labels, self.tonic.currentText(), self.mode.currentText(),
                         self.preset_box.currentData() or CUSTOM, self.active, freeze(self.values),
                         tuple(sorted(self.ipatterns.items())), tuple(sorted(self.ppatterns.items())),
                         self.restrike_box.isChecked(), self.melody_file, self.bass_file,
                         self.mel_inst_box.currentData(), self.mel_double_box.currentData() or "auto",
                         self.indep_box.isChecked(),
                         self.top_box.currentData(), self.keep_box.isChecked(), self.seed.value(),
                         tuple(self.alts), tuple(self.locks), self.tab, self.dirty,
                         tuple(tuple(r) for r in self.palts), tuple(self.ptabs),
                         phrase=self.phrase_box.currentData() or 4, emphasis=self.emphasis_box.isChecked(),
                         clear_low=self.clear_low_box.isChecked(), change_accents=self.change_accent_box.isChecked(),
                         theme=self.theme_box.isChecked(), expression=self._expression_state())

    def record(self, label: str):
        if not self._restoring:
            self.history.push(self.snapshot(), label)
        self._refresh_undo()

    def undo(self):
        state = self.history.undo()
        if state is not None:
            self.restore(state)
            self.statusBar().showMessage(f"Undone: {self.history.redo_label()}", 5000)

    def redo(self):
        state = self.history.redo()
        if state is not None:
            self.restore(state)
            self.statusBar().showMessage(f"Redone: {self.history.undo_label()}", 5000)

    def restore(self, st: EditState):
        self._restoring = True
        try:
            blocked = (self.tonic, self.mode, self.preset_box, self.forces, self.density, self.dynamics,
                       self.character, self.pattern_box, self.top_box, self.keep_box, self.seed, self.tabs,
                       self.restrike_box, self.indep_box, self.mel_inst_box, self.mel_double_box,
                       self.note_mode_box, self.accent_box, self.pattern_tabs, self.shape_box, self.fill_box,
                       self.phrase_box, self.emphasis_box, self.clear_low_box, self.change_accent_box, self.theme_box,
                       *self._expression_widgets())
            for w in blocked:
                w.blockSignals(True)
            self.mode.setCurrentText(st.mode)
            self._fill_tonics(st.tonic)
            if self.session is not None:
                if self.session.key != Key(st.tonic, st.mode):
                    self.session.set_key(Key(st.tonic, st.mode))
                for r, (corr, conf) in zip(self.session.results, st.labels):
                    r.correction, r.confirmed = corr, conf
            self._fill_presets(st.preset)
            self.active = st.active
            self.values = thaw(st.values)
            self.ipatterns, self.ppatterns = dict(st.ipatterns), dict(st.ppatterns)
            self.restrike_box.setChecked(st.restrike)
            self.phrase_box.setCurrentIndex(max(0, self.phrase_box.findData(st.phrase)))
            self.emphasis_box.setChecked(st.emphasis)
            self.clear_low_box.setChecked(st.clear_low)
            self.change_accent_box.setChecked(st.change_accents)
            self.theme_box.setChecked(st.theme)
            self._show_expression(st.expression)
            self.melody_file, self.bass_file = st.melody, st.bass
            self.indep_box.setChecked(st.independent)
            self._fill_melody_instruments(st.mel_inst)
            self.mel_double_box.setCurrentIndex(max(0, self.mel_double_box.findData(st.mel_double)))
            self._show_scope_values()
            self._show_slots()
            self.top_box.setCurrentIndex(self.top_box.findData(st.top_voice))
            self.keep_box.setChecked(st.keep)
            self.seed.setValue(st.seed)
            self.tabs.setCurrentIndex(st.tab)
            for w in blocked:
                w.blockSignals(False)
            self.alts, self.locks, self.tab, self.dirty = list(st.alts), list(st.locks), st.tab, st.dirty
            self.palts = [list(r) for r in (st.palts or NO_PALTS)]
            self.ptabs = list(st.ptabs or (0, 0, 0))
            self.pattern_tabs.setCurrentIndex(self.ptabs[self.tab])
            self._show_current()
        finally:
            self._restoring = False
        self._refresh()

    def _refresh_undo(self):
        u, r = self.history.can_undo(), self.history.can_redo()
        for w in (self.undo_btn, self.undo_action):
            w.setEnabled(u)
        for w in (self.redo_btn, self.redo_action):
            w.setEnabled(r)
        self.undo_btn.setToolTip(f"Undo {self.history.undo_label()} (Ctrl+Z)" if u else "Nothing to undo")
        self.redo_btn.setToolTip(f"Redo {self.history.redo_label()} (Ctrl+Y)" if r else "Nothing to redo")
        self._update_title()

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
            self.record(f"Key {self.key().label()}")
        self._refresh()

    # ------------------------------------------------------------------ files
    def open_dialog(self):
        start = self.projects_root if self.projects_root.exists() else Path.home()
        path, _ = QFileDialog.getOpenFileName(self, "Open chords or project", str(start),
                                              "Chords or projects (*.mid *.midi *.osk);;MIDI files (*.mid *.midi);;"
                                              "OrchSketch projects (*.osk)")
        if path:
            self.load(path)

    def load(self, path) -> bool:
        """Open a chord clip (.mid) as a new project, or an OrchSketch project (.osk)."""
        if str(path).lower().endswith(pj.SUFFIX):
            return self.open_project(path)
        if not self.confirm_discard():
            return False
        try:
            clip = read_chord_file(path)
            data = Path(path).read_bytes()
        except InputError as exc:
            QMessageBox.warning(self, "Can't use this file", str(exc))
            return False
        except OSError as exc:
            QMessageBox.warning(self, "Can't use this file", f"Couldn't read the file ({exc}).")
            return False
        self.chords_file = (Path(path).name, data)
        self.project_path = None
        self.session = AnalysisSession(clip, self.key())
        self.selected = None
        self.clear_orchestration()
        self.locks = [frozenset(), frozenset(), frozenset()]
        self.file_label.setText(f"{Path(path).name}  ·  {clip.bars} bars")
        self.file_label.setStyleSheet("")
        self.history.reset(self.snapshot(), "Open file")
        self._mark_saved()
        self._refresh()
        if clip.warnings:
            self.statusBar().showMessage(" ".join(dict.fromkeys(clip.warnings)), 10000)
        return True

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls() and any(u.toLocalFile().lower().endswith((".mid", ".midi", pj.SUFFIX))
                                          for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        for u in e.mimeData().urls():
            if u.toLocalFile().lower().endswith((".mid", ".midi", pj.SUFFIX)):
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

    def ask_text(self, title: str, label: str, text: str = "") -> str | None:
        """Ask for a line of text (separate method so tests can replace it)."""
        value, ok = QInputDialog.getText(self, title, label, text=text)
        return value if ok else None

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
        self.record(f"Chord {label.symbol(self.key())}")
        self._refresh()

    def type_chord_dialog(self, index: int):
        r = self.session.results[index]
        current = r.label.symbol(self.key()) if r.label else ""
        text = self.ask_text("Type a chord", "Chord symbol (e.g. Am7, C/E, Bbmaj7, F#m7b5, A5):", current)
        if text and text.strip():
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
        self.record("Back to best guess")
        self._refresh()

    def confirm_all(self):
        if not self.session:
            return
        unset = self.session.confirm_all()
        self.record("Confirm all")
        self._refresh()
        if unset:
            QMessageBox.information(self, "Some chords need you",
                                    f"{unset} chord(s) weren't recognized. Click the red ones and set them by hand.")

    def set_name_style(self, style: str):
        self.name_style = style
        self.settings.setValue("note_names", style)
        self._show_current()
        self._refresh()

    # ------------------------------------------------------------------ presets, parts, sliders
    def _apply_preset_values(self, p: Preset):
        sp = p.section_patterns()
        for sec in SECTIONS:
            for k in SLIDERS:
                self.values[sec][k] = p.section_value(sec, k)
            self.values[sec]["pattern"] = sp.get(sec, pat.SUSTAIN)
        self.ipatterns = p.instrument_patterns()
        self.ppatterns = {}
        self.active = frozenset(p.instruments)
        self._fill_melody_instruments(self.mel_inst_box.currentData() if hasattr(self, "mel_inst_box") else None)
        self._show_scope_values()

    def set_preset(self, pid: str):
        p = find(self.presets, pid)
        if p is None:
            return
        self._fill_presets(pid)
        old = self.render_settings()
        self._apply_preset_values(p)
        self.dirty = True
        if self.render_settings() != old:
            self._apply_render()
        self.record(f"Preset {p.name}")
        self._refresh()

    def _preset_chosen(self, index: int):
        pid = self.preset_box.itemData(index)
        if pid != CUSTOM:
            self.set_preset(pid)

    def build_parts_menu(self) -> QMenu:
        menu = QMenu(self)
        insts = instruments()
        for sec in SECTIONS:
            head = menu.addAction(sec.capitalize())
            head.setEnabled(False)
            for inst in sorted((i for i in insts.values() if i.section == sec), key=lambda i: i.order):
                a = menu.addAction("    " + inst.name)
                a.setCheckable(True)
                a.setChecked(inst.id in self.active)
                a.toggled.connect(lambda on, iid=inst.id: self.set_instrument(iid, on))
        return menu

    def set_instrument(self, inst_id: str, on: bool):
        new = self.active | {inst_id} if on else self.active - {inst_id}
        if not new:
            self.notify("No instruments", "At least one instrument has to play.")
            return
        if new == self.active:
            return
        self.active = frozenset(new)
        self._fill_presets(CUSTOM)
        for p in self.presets:  # back on a preset's exact line-up: show that preset
            if frozenset(p.instruments) == self.active:
                self._fill_presets(p.id)
                break
        self._fill_melody_instruments(self.mel_inst_box.currentData())
        self.dirty = True
        self.record(f"{'Add' if on else 'Remove'} {instruments()[inst_id].name}")
        self._refresh()

    def save_preset_dialog(self):
        name = self.ask_text("Save preset", "Name for your preset:")
        if name and name.strip():
            self.save_current_preset(name.strip())

    def save_current_preset(self, name: str) -> Preset:
        master = {k: self._master_and_overrides(k)[0] for k in SLIDERS}
        sections = tuple(sorted((sec, k, self.values[sec][k]) for sec in SECTIONS for k in SLIDERS
                                if self.values[sec][k] != master[k]))
        patterns = {sec: self.values[sec]["pattern"] for sec in SECTIONS if self.values[sec]["pattern"] != pat.SUSTAIN}
        patterns.update(self.ipatterns)
        p = Preset(preset_id(name), name, tuple(sorted(self.active)), master["forces"], master["density"],
                   master["dynamics"], master["character"], patterns=tuple(sorted(patterns.items())),
                   sections=sections)
        path = save_preset(p, self.presets_folder)
        self.presets, _ = load_all(self.presets_folder)
        self._fill_presets(p.id)
        self.statusBar().showMessage(f"Saved preset {name} to {path}", 10000)
        return p

    # ------------------------------------------------------------------ sliders (all sections or one)
    def scope_sections(self) -> list[str]:
        return list(SECTIONS) if self.scope == ALL else [self.scope]

    def set_scope(self, scope: str):
        self.scope = scope or ALL
        if self.scope_box.currentData() != self.scope:
            self.scope_box.blockSignals(True)
            self.scope_box.setCurrentIndex(self.scope_box.findData(self.scope))
            self.scope_box.blockSignals(False)
        self._show_scope_values()

    def _scope_value(self, key: str):
        vals = [self.values[sec][key] for sec in self.scope_sections()]
        return vals[0], len(set(vals)) > 1

    def _show_scope_values(self):
        """Show the scope's values on the sliders (\"mixed\" when the sections differ)."""
        if not hasattr(self, "character"):
            return
        for key, w, steps, names, lab in (
                ("character", self.character, CHARACTERS, CHARACTER_NAMES, self.character_label),
                ("forces", self.forces, FORCES, FORCE_NAMES, self.forces_label),
                ("density", self.density, DENSITY_STEPS, DENSITY_NAMES, self.density_label),
                ("dynamics", self.dynamics, DYNAMIC_STEPS, {d: d for d in DYNAMIC_STEPS}, self.dynamics_label)):
            v, mixed = self._scope_value(key)
            w.blockSignals(True)
            w.setValue(steps.index(v))
            w.blockSignals(False)
            lab.setText(names[v] + ("  (sections differ)" if mixed else ""))
        differ = []
        for key, box, name in (("note_mode", self.note_mode_box, "Note mode"), ("accent", self.accent_box, "Accents"),
                               ("shape", self.shape_box, "Shape"), ("fill", self.fill_box, "Fill"),
                               ("swell", self.swell_box, "Swell")):
            v, mixed = self._scope_value(key)
            box.blockSignals(True)
            box.setCurrentIndex(box.findData(v))
            box.blockSignals(False)
            if mixed:
                differ.append(f"{name}: sections differ")
        self.mode_label.setText(" · ".join(differ))
        self.mode_label.setVisible(bool(differ))
        v, mixed = self._scope_value("pattern")
        self.pattern_box.blockSignals(True)
        self.pattern_box.setCurrentIndex(self.pattern_box.findData(v))
        self.pattern_box.blockSignals(False)
        extra = []
        if mixed:
            extra.append("sections differ")
        insts = instruments()
        own = sorted({insts[i].name for i in self.ipatterns if insts[i].section in self.scope_sections()})
        if own:
            extra.append("own pattern: " + ", ".join(own))
        if self.ppatterns:
            extra.append(f"{len(self.ppatterns)} part(s) set by hand")
        self.pattern_label.setText(" · ".join(extra))

    def _update_slider_labels(self):
        self._show_scope_values()

    def _slider_moved(self, key: str, value):
        if self._restoring:
            return
        secs = self.scope_sections()
        if all(self.values[sec][key] == value for sec in secs) and not (
                key == "pattern" and (self.ipatterns or self.ppatterns)):
            self._show_scope_values()
            return
        for sec in secs:
            self.values[sec][key] = value
        insts = instruments()
        if key == "pattern":  # a section pattern replaces the preset's instrument patterns and your part ones
            self.ipatterns = {i: v for i, v in self.ipatterns.items() if insts[i].section not in secs}
            for o in self.alts:
                if isinstance(o, Orchestration):
                    for ln in o.lines:
                        if insts[ln.instrument].section in secs:
                            self.ppatterns.pop(ln.id, None)
        where = "" if self.scope == ALL else f" ({self.scope})"
        name = {"character": "Character", "forces": "Forces", "density": "Density", "dynamics": "Dynamics",
                "pattern": "Pattern", "note_mode": "Note mode", "accent": "Accents", "shape": "Shape",
                "fill": "Fill", "swell": "Swell"}[key]
        shown = (pat.PATTERN_NAMES[value] if key == "pattern" else pat.NOTE_MODE_NAMES[value] if key == "note_mode"
                 else pat.ACCENT_NAMES[value] if key == "accent" else shp.SHAPE_NAMES[value] if key == "shape"
                 else FILL_NAMES[value] if key == "fill" else ex.SWELL_NAMES[value] if key == "swell"
                 else CHARACTER_NAMES.get(value, value))
        self._show_scope_values()
        if key in RENDER_KEYS:
            self._apply_render()
            self.record(f"{name} {shown}{where}")
            self._refresh()
        else:
            self._setting_changed(f"{name} {shown}{where}")

    def _setting_changed(self, name: str):
        """A generation setting changed: it takes effect at the next Generate."""
        if self._restoring:
            return
        self.dirty = True
        self.record(name)
        self._refresh()

    def _extra_toggled(self, name: str, on: bool):
        """A render-only option outside the per-section values (phrase, emphasis, low register, accents)."""
        if self._restoring:
            return
        self._apply_render()
        self.record(name + ("" if on else " off"))
        self._refresh()

    def _restrike_toggled(self, on: bool):
        if self._restoring:
            return
        self._apply_render()
        self.record("Re-strike every bar" if on else "Hold ties")
        self._refresh()

    def set_part_pattern(self, line_id: str, pattern: str | None):
        """Give one part its own pattern (None: back to its section's)."""
        if pattern is None:
            self.ppatterns.pop(line_id, None)
        else:
            self.ppatterns[line_id] = pattern
        self._apply_render()
        label = self.orch.line(line_id).label if self.orch else line_id
        self.record(f"{label}: " + (pat.PATTERN_NAMES[pattern] if pattern else "section pattern"))
        self._show_scope_values()
        self._refresh()

    def _apply_render(self):
        """Apply dynamics, patterns and re-strike to every alternative at once (no regeneration)."""
        rs = self.render_settings()
        self.alts = [rerender(o, replace(o.settings, **rs)) if isinstance(o, Orchestration) else o
                     for o in self.alts]
        # patterns 2 and 3 follow the new pattern settings (same variation, locked parts keep their choices)
        for t, row in enumerate(self.palts):
            h = self.alts[t]
            self.palts[t] = [None] + [pa.refresh(p, h, self.locks[t]) if isinstance(p, Orchestration)
                                      and isinstance(h, Orchestration) else None for p in row[1:]]
        self._ensure_pattern_alt()
        if self.orch is not None:
            self._show_current()
        if self.orch is not None and self.player is not None and self.player.seq is not None:
            self._load_player()

    def _apply_dynamics(self):
        self._apply_render()

    # ------------------------------------------------------------------ melody and bass files
    def _fill_melody_instruments(self, current: str | None):
        if not hasattr(self, "mel_inst_box"):
            return
        insts = instruments()
        hosts = list(dict.fromkeys(i for a in APPROACHES for i in MELODY_HOSTS[a]))
        self.mel_inst_box.blockSignals(True)
        self.mel_inst_box.clear()
        self.mel_inst_box.addItem("Melody: auto", None)
        for iid in hosts:
            if iid in self.active:
                self.mel_inst_box.addItem(f"Melody: {insts[iid].name}", iid)
        idx = self.mel_inst_box.findData(current)
        self.mel_inst_box.setCurrentIndex(idx if idx >= 0 else 0)
        self.mel_inst_box.blockSignals(False)

    def open_part_dialog(self, kind: str):
        path, _ = QFileDialog.getOpenFileName(self, f"Open {kind} MIDI", str(Path.home()), "MIDI files (*.mid *.midi)")
        if path:
            self.load_part_file(kind, path)

    def load_part_file(self, kind: str, path) -> bool:
        """Load a melody or bass file into its slot (monophonic, starts with the chords)."""
        try:
            clip = read_monophonic_file(path, kind.capitalize())
            data = Path(path).read_bytes()
        except InputError as exc:
            self.notify("Can't use this file", str(exc))
            return False
        except OSError as exc:
            self.notify("Can't use this file", f"Couldn't read the file ({exc}).")
            return False
        entry = (Path(path).name, tuple(clip.notes), data)
        if kind == "melody":
            self.melody_file = entry
        else:
            self.bass_file = entry
        if self.session is not None and clip.notes and max(n.end for n in clip.notes) > self.session.clip.length:
            self.statusBar().showMessage(f"The {kind} file is longer than the chords: notes after bar "
                                         f"{self.session.clip.bars} are left out.", 10000)
        self._show_slots()
        self._setting_changed(f"{kind.capitalize()} file {Path(path).name}")
        return True

    def clear_part_file(self, kind: str):
        if (self.melody_file if kind == "melody" else self.bass_file) is None:
            return
        if kind == "melody":
            self.melody_file = None
        else:
            self.bass_file = None
        self._show_slots()
        self._setting_changed(f"Remove {kind} file")

    def _show_slots(self):
        for kind, entry in (("melody", self.melody_file), ("bass", self.bass_file)):
            lab = self.slot_label[kind]
            lab.setText(entry[0] if entry else "none")
            lab.setStyleSheet("" if entry else f"color: {MUTED};")
            self.slot_clear[kind].setEnabled(entry is not None)
        has_mel = self.melody_file is not None
        self.mel_inst_box.setEnabled(has_mel)
        self.mel_double_box.setEnabled(has_mel)
        self.indep_box.setEnabled(self.bass_file is None)

    # ------------------------------------------------------------------ display
    def _refresh(self):
        key = self.key()
        has = self.session is not None
        self.confirm_btn.setEnabled(has)
        ready = has and self.session.all_confirmed and bool(self.session.chord_results)
        busy = self._job is not None
        self.generate_btn.setEnabled(ready and not busy)
        if busy:
            self.generate_btn.setText("Generating…")
        else:
            self.generate_btn.setText("Generate •" if self.dirty and any(self.alts) else "Generate")
        self.generate_btn.setStyleSheet("QPushButton { font-weight: 600; }" + (
            " QPushButton:enabled { background: #7a5b17; }" if self.dirty and any(self.alts) and not busy else ""))
        self.generate_btn.setToolTip(
            "Settings changed: press Generate to build the alternatives with them" if self.dirty and any(self.alts)
            else "Orchestrate the confirmed chords as alternatives A, B and C" if ready
            else "Confirm every chord first (Confirm all)")
        for w in (self.play_btn, self.export_parts_btn, self.all_handle, self.regen_btn):
            w.setEnabled(self.orch is not None and not busy)
        patterned = self.harmony is not None and bool(pa.groups(self.harmony))
        self.pattern_tabs.setEnabled(self.harmony is not None and not busy)
        for k in (1, 2):
            self.pattern_tabs.setTabEnabled(k, patterned or self.ptabs[self.tab] == k)
        self.pattern_tabs.setTabToolTip(1, "" if patterned else "Give a section a rhythm pattern first")
        self.pattern_tabs.setTabToolTip(2, "" if patterned else "Give a section a rhythm pattern first")
        self.regen_patterns_btn.setEnabled(self.orch is not None and not busy and self.ptabs[self.tab] > 0)
        self.strip.show_results(self.session.results if has else [], key, self.selected)
        self.details.setHtml(self._details_html(key))
        for i, a in enumerate(APPROACHES):
            o = self.alts[i]
            mark = "" if isinstance(o, Orchestration) else (" ⚠" if isinstance(o, str) else "")
            self.tabs.setTabText(i, f"{a} · {APPROACH[a].name}{mark}")
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
        self._refresh_undo()

    def _details_html(self, key: Key) -> str:
        if not self.session:
            return (f"<p style='color:{MUTED}'>Export the chord clip from Ableton (right-click the clip "
                    "&gt; Export MIDI Clip), then drop it here. Set the key and mode first or after - "
                    "labels update either way.</p>")
        if self.selected is None:
            o = self.orch
            if o is not None and o.report.issues:
                rows = [o.report.summary()] + [
                    f"<span style='color:{'#e05252' if i.severity == 'error' else '#e6c84f'}'>"
                    f"{i.severity}</span> {i.message}" for i in o.report.issues[:60]]
                return "<br>".join(rows)
            return (f"<p style='color:{MUTED}'>Click a chord to see its notes and alternatives. In the grid, "
                    "click a chord header to regenerate or swap it, and right-click a part to lock or "
                    "regenerate it.</p>")
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

    def _show_current(self):
        """Show the current tab's alternative in the grid, reason line and checker summary."""
        self._ensure_pattern_alt()
        o = self.orch if self.harmony is not None else self.alts[self.tab]
        if self.pattern_tabs.currentIndex() != self.ptabs[self.tab]:
            self.pattern_tabs.blockSignals(True)
            self.pattern_tabs.setCurrentIndex(self.ptabs[self.tab])
            self.pattern_tabs.blockSignals(False)
        if isinstance(o, Orchestration):
            self.grid.show_orchestration(o, self.key(), self.name_style, self.locks[self.tab])
            self.checker_label.setText(o.report.summary() + (
                "  (red cells come from your own edits; Ctrl+Z undoes them)" if o.report.errors else ""))
            patterns = pa.describe(o)
            self.reason_label.setText(f"{pa.alt_name(o)} · {o.reason}" + (f" Patterns: {patterns}." if patterns
                                                                          else ""))
            sel = self.grid.line_ids[0] if self.grid.line_ids else None
            if sel:
                self.grid.select_part(sel)
        elif isinstance(o, str):
            self.grid.clear_grid(f"Alternative {self.approach} couldn't be built: {o}")
            self.checker_label.setText("")
            self.reason_label.setText("")
            self.piano.clear_part()
        else:
            self.grid.clear_grid("Confirm the chords, then press Generate." if not any(self.alts)
                                 else "Press Generate.")
            self.checker_label.setText("")
            self.reason_label.setText("")
            self.piano.clear_part()
        self.muted, self.soloed = set(), set()
        for b in list(self.section_mute.values()) + list(self.section_solo.values()):
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        if self.player is not None:
            if self.orch is not None and self.player.seq is not None:
                self._load_player()
            elif self.orch is None:
                self.stop()
                self.player.seq = None

    def set_pattern_tab(self, index: int):
        """Show pattern alternative 1, 2 or 3 (index 0-2) of the current harmony alternative."""
        if self._restoring:
            return
        self.ptabs[self.tab] = index
        if self.pattern_tabs.currentIndex() != index:
            self.pattern_tabs.blockSignals(True)
            self.pattern_tabs.setCurrentIndex(index)
            self.pattern_tabs.blockSignals(False)
        self._show_current()
        self._refresh()

    def regenerate_patterns_action(self):
        """New choices for the shown pattern alternative (2 or 3); locked parts keep their patterns."""
        k = self.ptabs[self.tab]
        h, cur = self.harmony, self.orch
        if h is None or not k:
            self.notify("Pick patterns 2 or 3", "Patterns 1 is exactly your own pattern settings. Choose Patterns 2 "
                                                "or 3 to get other patterns, then regenerate them.")
            return None
        new = pa.regenerate_patterns(cur, h, self.locks[self.tab])
        row = list(self.palts[self.tab])
        row[k] = new
        self.palts[self.tab] = row
        self._show_current()
        self.record(f"Regenerate patterns {pa.alt_name(new)}")
        self._refresh()
        return new

    def set_tab(self, index: int):
        self.tab = index
        if self.tabs.currentIndex() != index:
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(index)
            self.tabs.blockSignals(False)
        self._show_current()
        self._refresh()

    # ------------------------------------------------------------------ messages (replaceable in tests)
    def notify(self, title: str, text: str):
        QMessageBox.information(self, title, text)

    def open_folder(self, path: Path):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # ------------------------------------------------------------------ generate
    def generate(self):
        """Build A, B and C (in the background). Locked parts of each alternative are kept."""
        if not self.session:
            self.notify("Nothing to orchestrate", "Open a chord file first.")
            return None
        if not self.session.all_confirmed:
            self.notify("Confirm the chords first",
                        "Generation only uses confirmed chords. Click Confirm all (or confirm each chord).")
            return None
        if self._job is not None:
            return None
        chords = chords_from_session(self.session)
        settings = self.gen_settings()
        previous = {a: (o if isinstance(o, Orchestration) else None) for a, o in zip(APPROACHES, self.alts)}
        locks = {a: lk for a, lk in zip(APPROACHES, self.locks)}
        args = (chords, self.key())
        kwargs = dict(seed=self.seed.value(), settings=settings, locks=locks, previous=previous,
                      parallel=self.parallel)
        if not self.run_async:
            return self._generated(generate_all(*args, **kwargs))
        self._job = self._pool.submit(generate_all, *args, **kwargs)
        self.statusBar().showMessage("Generating alternatives A, B and C…")
        QApplication.setOverrideCursor(Qt.BusyCursor)
        self.job_timer.start()
        self._refresh()
        return None

    def _poll_job(self):
        if self._job is None or not self._job.done():
            return
        job, self._job = self._job, None
        self.job_timer.stop()
        QApplication.restoreOverrideCursor()
        try:
            result = job.result()
        except Exception as exc:  # noqa: BLE001 - shown to the user, logged by the app's hook
            self.notify("Couldn't orchestrate", f"Something went wrong: {exc}")
            self._refresh()
            return
        self._generated(result)

    def wait_for_generation(self, timeout: float = 120.0):
        """Block until a background Generate has finished and been shown (for tests and scripts)."""
        if self._job is not None:
            self._job.result(timeout=timeout)
            self._poll_job()

    def _generated(self, result: dict):
        self.stop()
        self.alts = [result[a] if isinstance(result[a], Orchestration) else str(result[a]) for a in APPROACHES]
        self.palts = [[None, None, None] for _ in range(3)]  # built again on demand for the new harmony
        # locks only make sense for parts that still exist
        self.locks = [frozenset(lid for lid in lk if isinstance(o, Orchestration) and lid in o.cells)
                      for lk, o in zip(self.locks, self.alts)]
        self.dirty = False
        self.statusBar().showMessage("Generated alternatives A, B and C.", 5000)
        failed = [(a, o) for a, o in zip(APPROACHES, self.alts) if isinstance(o, str)]
        if len(failed) == 3:
            self.notify("Couldn't orchestrate", failed[0][1])
        elif failed:
            self.statusBar().showMessage(" ".join(f"{a}: {msg}" for a, msg in failed), 15000)
        self.piano.clear_part()
        self.selected = None
        self._show_current()
        self.record("Generate")
        self._refresh()
        return self.orch

    def clear_orchestration(self, message: str | None = None):
        if not any(self.alts):
            self.grid.clear_grid()
            return
        self.stop()
        self.alts = [None, None, None]
        self.palts = [[None, None, None] for _ in range(3)]
        self.locks = [frozenset(), frozenset(), frozenset()]
        self.grid.clear_grid(message or "Confirm the chords, then press Generate.")
        self.piano.clear_part()
        self.checker_label.setText("")
        self.reason_label.setText("")
        if self.player is not None:
            self.player.seq = None

    # ------------------------------------------------------------------ edits on the current alternative
    def _edit(self, label: str, fn) -> Orchestration | None:
        o = self.harmony
        if o is None:
            return None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            new = fn(o)
        except GenerationError as exc:
            QApplication.restoreOverrideCursor()
            self.notify("Can't do that here", str(exc))
            return None
        QApplication.restoreOverrideCursor()
        self.alts[self.tab] = new
        # patterns 2 and 3 keep their choices on the edited harmony
        self.palts[self.tab] = [None] + [pa.reapply(p, new) if isinstance(p, Orchestration) else None
                                         for p in self.palts[self.tab][1:]]
        self._show_current()
        self.record(label)
        self._refresh()
        if new.report.errors:
            self.statusBar().showMessage("This edit breaks a rule (red cells). Ctrl+Z undoes it.", 10000)
        return new

    def regenerate_unlocked(self):
        lk = self.locks[self.tab]
        return self._edit(f"Regenerate {self.approach}", lambda o: regenerate(o, lk))

    def regenerate_one_part(self, line_id: str):
        name = self.orch.line(line_id).label if self.orch else line_id
        return self._edit(f"Regenerate {name}", lambda o: regenerate_part(o, line_id))

    def regenerate_one_chord(self, index: int):
        lk = self.locks[self.tab]
        return self._edit(f"Regenerate chord {index + 1}", lambda o: regenerate_chord(o, index, lk))

    def swap_from(self, source: str, index: int, whole_bar: bool = False):
        src = self.alts[APPROACHES.index(source)]
        if not isinstance(src, Orchestration):
            self.notify("Nothing to swap", f"Alternative {source} hasn't been built.")
            return None
        lk = self.locks[self.tab]
        what = f"bar {self.orch.chords[index].start // 1920 + 1}" if whole_bar else f"chord {index + 1}"

        def do(o):
            idx = bar_chords(o, index) if whole_bar else [index]
            return swap(o, src, idx, lk)
        return self._edit(f"Use {source} for {what}", do)

    def set_lock(self, line_id: str, on: bool):
        if self._restoring or self.orch is None:
            return
        lk = self.locks[self.tab]
        self.locks[self.tab] = lk | {line_id} if on else lk - {line_id}
        # don't rebuild the grid here: the lock button that sent this signal lives in it
        self.grid.set_locked(line_id, on, self.orch.line(line_id).label)
        self.record(f"{'Lock' if on else 'Unlock'} {self.orch.line(line_id).label}")

    def build_column_menu(self, index: int) -> QMenu:
        menu = QMenu(self)
        o = self.orch
        if o is None:
            return menu
        span = o.chords[index]
        head = menu.addAction(f"{span.label.symbol(self.key())} (chord {index + 1})")
        head.setEnabled(False)
        a = menu.addAction("Regenerate this chord")
        a.triggered.connect(lambda: self.regenerate_one_chord(index))
        menu.addSeparator()
        for src in APPROACHES:
            if src == o.approach and all(s == o.approach for s in o.sources):
                continue
            ok = isinstance(self.alts[APPROACHES.index(src)], Orchestration)
            a1 = menu.addAction(f"Use {src}'s voicing for this chord" + (" (back to own)" if src == o.approach else ""))
            a1.setEnabled(ok)
            a1.triggered.connect(lambda _=False, s=src: self.swap_from(s, index))
            a2 = menu.addAction(f"Use {src}'s voicing for this bar")
            a2.setEnabled(ok)
            a2.triggered.connect(lambda _=False, s=src: self.swap_from(s, index, whole_bar=True))
        return menu

    def build_part_menu(self, line_id: str, index: int = -1) -> QMenu:
        menu = QMenu(self)
        o = self.orch
        if o is None:
            return menu
        ln = o.line(line_id)
        locked = line_id in self.locks[self.tab]
        a = menu.addAction(("Unlock " if locked else "Lock ") + ln.label)
        a.triggered.connect(lambda: self.grid.lock_buttons[line_id].setChecked(not locked)
                            if line_id in self.grid.lock_buttons else self.set_lock(line_id, not locked))
        a = menu.addAction(f"Regenerate {ln.label} only")
        a.setEnabled(not locked and bool(o.part(line_id).notes) and line_id not in o.figures)
        a.triggered.connect(lambda: self.regenerate_one_part(line_id))
        sec = instruments()[ln.instrument].section
        if line_id in o.figures:
            a = menu.addAction("Pattern: plays your " + ("melody" if ln.role == "melody" else "bass") + " file's rhythm")
            a.setEnabled(False)
        else:
            sub = menu.addMenu("Pattern")
            section_pt = self.values[sec]["pattern"]
            own = self.ppatterns.get(line_id)
            d = sub.addAction(f"Section's pattern ({pat.PATTERN_NAMES[self.ipatterns.get(ln.instrument, section_pt)]})")
            d.setCheckable(True)
            d.setChecked(own is None)
            d.triggered.connect(lambda _=False: self.set_part_pattern(line_id, None))
            sub.addSeparator()
            for pt in pat.PATTERNS:
                if not pat.allowed(pt, sec == "choir"):
                    continue
                act = sub.addAction(pat.PATTERN_NAMES[pt])
                act.setCheckable(True)
                act.setChecked(own == pt)
                act.triggered.connect(lambda _=False, x=pt: self.set_part_pattern(line_id, x))
        if index >= 0:
            menu.addSeparator()
            sub = self.build_column_menu(index)
            for act in sub.actions():
                act.setParent(menu)
                menu.addAction(act)
        return menu

    # ------------------------------------------------------------------ part display
    def show_part(self, line_id: str):
        if not self.orch:
            return
        ln = self.orch.line(line_id)
        notes = self.orch.part(line_id).notes
        groups = ex.split_notes(self.orch.meta, line_id, notes)
        kinds = {n: k for k in ("trem", "rise") for n in groups[k]}
        self.piano.set_part(ln.label, notes, self.session.clip.length,
                            [c.start for c in self.orch.chords], self.name_style, self.key(),
                            curves=self.orch.curves_for(line_id), cc1=self.orch.cc1_for(line_id), kinds=kinds)

    # ------------------------------------------------------------------ playback
    def _load_player(self):
        insts = instruments()
        lines = self.orch.sounding_lines
        orch = self.orch
        hz = orch.settings.humanize
        parts, controls = [], {}
        for ln in lines:
            prog = ln.program if ln.program is not None else insts[ln.instrument].gm_program
            notes = list(orch.part(ln.id).notes)
            curve = orch.curves_for(ln.id)
            if not orch.meta.get("expression") and hz == ex.HUMANIZE_OFF:
                parts.append((ln.id, prog, notes))  # v1.3 exactly
                continue
            groups = ex.split_notes(orch.meta, ln.id, notes)
            if hz != ex.HUMANIZE_OFF:  # the same offsets as the export
                groups = {k: ex.humanize(v, ex.humanize_key(orch.seed, pa.alt_name(orch), ln.id, k), hz)
                          for k, v in groups.items()}
            parts.append((ln.id, prog, groups[""] + groups["rise"]))
            if groups["trem"]:
                parts.append((ln.id + "/trem", ex.TREMOLO_PROGRAM, groups["trem"]))
            if curve:
                controls[ln.id] = controls[ln.id + "/trem"] = ex.audition_expression(curve)
        sections = {ln.id: insts[ln.instrument].section for ln in lines}
        self.player.loop = self.loop_box.isChecked()
        self.player.set_bpm(self.tempo.value())
        self.player.load(parts, self.session.clip.length, sections, controls or None)
        for pid in self.muted:
            if pid in sections:
                self.player.seq.set_mute(pid, True)
        for pid in self.soloed:
            if pid in sections:
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
        if hasattr(self, "undo_btn"):
            self._update_title()

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
        """The .osk file's name once saved, else the chord clip's name."""
        if self.project_path is not None:
            return self.project_path.stem
        if self.chords_file is not None:
            return Path(self.chords_file[0]).stem
        return Path(self.session.clip.source_path).stem if self.session else "OrchSketch"

    def parts_folder(self) -> Path:
        return export_folder(self.project_name(), self.export_root)

    def files_for_part(self, line_id: str) -> list[Path]:
        if not self.orch:
            return []
        return export_part_files(self.orch, line_id, self.parts_folder(), self.project_name(), self.tempo.value(),
                                 self.session.clip.length)

    def files_for_all(self) -> list[Path]:
        """What the All handle drags and Export writes: the export choice (+ combined divisi files)."""
        if not self.orch:
            return []
        return export_all(self.orch, self.parts_folder(), self.project_name(), self.tempo.value(),
                          self.session.clip.length, self.export_box.currentData() or BOTH,
                          self.combined_box.isChecked())

    def export_parts_action(self) -> list[Path]:
        if not self.orch:
            self.notify("Nothing to export", "Generate an orchestration first.")
            return []
        files = self.files_for_all()
        folder = self.parts_folder()
        self.statusBar().showMessage(f"Exported {len(files)} files of alternative {pa.alt_name(self.orch)} to {folder}",
                                     15000)
        self.open_folder(folder)
        return files

    # ------------------------------------------------------------------ projects (.osk)
    def has_unsaved_changes(self) -> bool:
        """Edits since the last save/open, or a new tempo. Undoing back to the saved state counts as saved."""
        return self.history.current is not self._saved or self.tempo.value() != self._saved_tempo

    def _worth_keeping(self) -> bool:
        """Only ask before discarding something real: an orchestration, or a project that has a file."""
        return self.has_unsaved_changes() and (any(self.alts) or self.project_path is not None)

    def _mark_saved(self):
        self._saved = self.history.current
        self._saved_tempo = self.tempo.value()
        self._update_title()

    def _update_title(self):
        name = self.project_name() if self.session else None
        star = " *" if self.session is not None and self.has_unsaved_changes() else ""
        self.setWindowTitle(f"OrchSketch {__version__}" + (f" - {name}{star}" if name else ""))

    def ask_save(self) -> str:
        """Save / discard / cancel. Replaceable (tests never open a dialog)."""
        r = QMessageBox.question(self, "Unsaved changes", f"Save the changes to {self.project_name()}?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        return {QMessageBox.Save: SAVE, QMessageBox.Discard: DISCARD}.get(r, CANCEL)

    def ask_save_path(self, default: Path) -> Path | None:
        """Where to save the project. Replaceable (tests never open a dialog)."""
        default.parent.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Save project", str(default), "OrchSketch projects (*.osk)")
        return Path(path) if path else None

    def confirm_discard(self) -> bool:
        """Before throwing the current work away: True to go on (saved or discarded), False to stop."""
        if not self._worth_keeping():
            return True
        answer = self.ask_save()
        if answer == SAVE:
            return self.save_project() is not None
        return answer == DISCARD

    def new_project(self) -> bool:
        if not self.confirm_discard():
            return False
        self.stop()
        self.session = None
        self.chords_file = None
        self.project_path = None
        self.selected = None
        self.clear_orchestration()
        self.melody_file = self.bass_file = None
        self.file_label.setText("No file")
        self.file_label.setStyleSheet(f"color: {MUTED};")
        self._show_slots()
        self.history.reset(self.snapshot(), "New project")
        self._mark_saved()
        self._refresh()
        self._refresh_undo()
        return True

    def to_project(self) -> pj.Project:
        st = self.snapshot()

        def inp(entry):
            return None if entry is None else pj.InputFile(entry[0], entry[2] if len(entry) > 2 else b"",
                                                           tuple(entry[1]))
        return pj.Project(
            chords=pj.InputFile(*self.chords_file) if self.chords_file else pj.InputFile("chords.mid"),
            clip=self.session.clip, tempo=self.tempo.value(), loop=self.loop_box.isChecked(),
            labels=st.labels, tonic=st.tonic, mode=st.mode, preset=st.preset, active=st.active, values=st.values,
            ipatterns=st.ipatterns, ppatterns=st.ppatterns, restrike=st.restrike, melody=inp(st.melody),
            bass=inp(st.bass), mel_inst=st.mel_inst, mel_double=st.mel_double, independent=st.independent,
            top_voice=st.top_voice, keep=st.keep, seed=st.seed, alts=st.alts, locks=st.locks, tab=st.tab,
            dirty=st.dirty, scope=self.scope, palts=st.palts, ptabs=st.ptabs, phrase=st.phrase,
            emphasis=st.emphasis, clear_low=st.clear_low, change_accents=st.change_accents, theme=st.theme,
            expression=st.expression)

    def save_project(self) -> Path | None:
        """Save to the project's file (asks where the first time). Returns the path, or None if cancelled."""
        if self.session is None:
            self.notify("Nothing to save", "Open a chord file first.")
            return None
        if self.project_path is None:
            return self.save_project_as()
        return self._write_project(self.project_path)

    def save_project_as(self) -> Path | None:
        if self.session is None:
            self.notify("Nothing to save", "Open a chord file first.")
            return None
        path = self.ask_save_path(self.projects_root / f"{safe_name(self.project_name())}{pj.SUFFIX}")
        return self._write_project(path) if path else None

    def _write_project(self, path: Path) -> Path | None:
        try:
            out = pj.save(self.to_project(), path)
        except OSError as exc:
            self.notify("Couldn't save the project", str(exc))
            return None
        self.project_path = out
        self._mark_saved()
        self.statusBar().showMessage(f"Saved {out}", 8000)
        return out

    def open_project(self, path) -> bool:
        if not self.confirm_discard():
            return False
        try:
            p = pj.load(path)
        except pj.ProjectError as exc:
            self.notify("Can't open this project", str(exc))
            return False
        self.stop()
        self.session = AnalysisSession(p.clip, Key(p.tonic, p.mode))
        self.chords_file = (p.chords.name, p.chords.data)
        self.project_path = Path(path)
        self.selected = None
        self.piano.clear_part()
        self.clear_orchestration()

        def entry(f):
            return None if f is None else (f.name, tuple(f.notes), f.data)
        st = EditState(tuple(p.labels), p.tonic, p.mode, p.preset, frozenset(p.active), tuple(p.values),
                       tuple(p.ipatterns), tuple(p.ppatterns), p.restrike, entry(p.melody), entry(p.bass), p.mel_inst,
                       p.mel_double, p.independent, p.top_voice, p.keep, p.seed, tuple(p.alts), tuple(p.locks),
                       p.tab, p.dirty, tuple(tuple(r) for r in p.palts), tuple(p.ptabs), phrase=p.phrase,
                       emphasis=p.emphasis, clear_low=p.clear_low, change_accents=p.change_accents, theme=p.theme,
                       expression=tuple(tuple(x) for x in p.expression))
        self.tempo.blockSignals(True)
        self.tempo.setValue(int(round(p.tempo)))
        self.tempo.blockSignals(False)
        self.loop_box.setChecked(p.loop)
        self.restore(st)
        self.set_scope(p.scope if p.scope in (ALL, *SECTIONS) else ALL)
        self.file_label.setText(f"{p.chords.name}  ·  {p.clip.bars} bars")
        self.file_label.setStyleSheet("")
        self.history.reset(self.snapshot(), "Open project")
        self._mark_saved()
        self._refresh_undo()
        n_saved = len(p.labels)
        if n_saved and n_saved != len(self.session.results):
            self.statusBar().showMessage("This version splits the chords differently; check the chord labels.", 15000)
        else:
            self.statusBar().showMessage(f"Opened {Path(path).name}", 8000)
        return True

    def closeEvent(self, e):  # noqa: N802
        if not self.confirm_discard():
            e.ignore()
            return
        if self._job is not None:
            self._job.cancel()
        self._pool.shutdown(wait=False, cancel_futures=True)
        if self.player is not None:
            self.player.close()
        super().closeEvent(e)
