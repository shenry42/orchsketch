"""Start the OrchSketch window."""
import sys
import traceback
from datetime import datetime
from pathlib import Path

LOG_DIR = Path.home() / "Documents" / "OrchSketch" / "logs"


def _install_error_log():
    """Unexpected errors go to Documents\\OrchSketch\\logs\\error_log.txt and a message box."""

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOG_DIR / "error_log.txt", "a", encoding="utf-8") as f:
                f.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} ===\n{text}")
        except OSError:
            pass
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "OrchSketch error",
                                 f"Something went wrong. Details were saved to\n{LOG_DIR / 'error_log.txt'}\n\n{exc}")
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook


def main() -> int:
    if "--self-check" in sys.argv:  # packaged-build check (Milestone 6): no window
        from .selfcheck import main as self_check
        return self_check(sys.argv)
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow
    from .ui.theme import apply_dark_theme

    _install_error_log()
    app = QApplication(sys.argv)
    app.setApplicationName("OrchSketch")
    apply_dark_theme(app)
    win = MainWindow()
    from . import parallel
    parallel.warm()  # start the A/B/C worker processes while the window opens
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:  # a .mid or .osk file (e.g. double-clicked)
        win.load(args[0])
    win.show()
    try:
        return app.exec()
    finally:
        parallel.shutdown()


if __name__ == "__main__":
    sys.exit(main())
