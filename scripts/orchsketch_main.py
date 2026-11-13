"""Entry point for the packaged app (PyInstaller). Same as `python -m orchsketch`."""
import multiprocessing
import sys

from orchsketch.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()  # A/B/C worker processes (orchsketch.parallel) start this exe again
    sys.exit(main())
