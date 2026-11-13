import multiprocessing
import sys

from .app import main

if __name__ == "__main__":  # worker processes (parallel.py) import this module again: don't start a window there
    multiprocessing.freeze_support()
    sys.exit(main())
