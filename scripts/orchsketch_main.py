"""Entry point for the packaged app (PyInstaller). Same as `python -m orchsketch`."""
import sys

from orchsketch.app import main

if __name__ == "__main__":
    sys.exit(main())
