"""Dark theme (SPEC §6)."""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

BG = "#1e1f22"
PANEL = "#2b2d31"
TEXT = "#e6e6e6"
MUTED = "#9a9ca3"
ACCENT = "#5b9bd5"
STATUS_COLORS = {
    "auto": "#6b6e76",  # grey: best guess, not confirmed yet
    "confirmed": "#4caf50",  # green
    "corrected": "#5b9bd5",  # blue
    "unrecognized": "#e05252",  # red: must be set by hand
}


def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    roles = {
        QPalette.Window: BG, QPalette.WindowText: TEXT, QPalette.Base: "#232428",
        QPalette.AlternateBase: PANEL, QPalette.ToolTipBase: PANEL, QPalette.ToolTipText: TEXT,
        QPalette.Text: TEXT, QPalette.Button: PANEL, QPalette.ButtonText: TEXT,
        QPalette.BrightText: "#ffffff", QPalette.Highlight: ACCENT, QPalette.HighlightedText: "#ffffff",
        QPalette.PlaceholderText: MUTED,
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(MUTED))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(MUTED))
    app.setPalette(pal)
    app.setStyleSheet(
        f"QToolTip {{ color: {TEXT}; background: {PANEL}; border: 1px solid #444; }}"
        f"QPushButton {{ padding: 5px 12px; }}"
    )
