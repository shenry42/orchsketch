"""Build A, B and C in parallel processes (v1.3 speed fix).

Each approach is generated in its own worker process, so Generate takes about as long as the slowest approach
instead of all three together. Generation is deterministic, so the result is exactly what `generate_all` gives
in one process (tests compare them note for note).

The pool is started once (`warm()`, called when the window opens) and reused, so Generate doesn't pay the
process start-up (about 0.5 s on Windows). If the pool can't be started or a worker dies, Generate falls back
to building the alternatives one after another in this process. The packaged app needs
`multiprocessing.freeze_support()` in its entry point (scripts/orchsketch_main.py).
"""
from __future__ import annotations

import multiprocessing as mp
import threading
from concurrent.futures import Future, ProcessPoolExecutor

WORKERS = 3  # one per approach

_pool: ProcessPoolExecutor | None = None
_lock = threading.Lock()
_failed = False  # the pool couldn't be used: stay in one process for the rest of the session


def _ready() -> bool:
    """Runs in a worker: import the generator (and load its data) so the first Generate is fast."""
    from . import generator
    generator.builtin_rules()
    generator.builtin_instruments()
    return True


def pool() -> ProcessPoolExecutor | None:
    global _pool, _failed
    with _lock:
        if _failed:
            return None
        if _pool is None:
            try:
                _pool = ProcessPoolExecutor(max_workers=WORKERS, mp_context=mp.get_context("spawn"))
            except Exception:  # noqa: BLE001 - fall back to one process
                _failed = True
                return None
        return _pool


def warm() -> list[Future]:
    """Start the worker processes in the background (each imports the generator)."""
    p = pool()
    if p is None:
        return []
    try:
        return [p.submit(_ready) for _ in range(WORKERS)]
    except Exception:  # noqa: BLE001
        _broken()
        return []


def _broken():
    global _pool, _failed
    with _lock:
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None
        _failed = True


def shutdown():
    global _pool
    with _lock:
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=True)
        _pool = None


def map_approaches(fn, jobs: dict):
    """Run fn(**kwargs) for each approach in the pool: {approach: kwargs} -> {approach: result or exception}.

    Returns None when the pool isn't available or failed, so the caller runs the jobs itself. fn returns its
    own expected errors (generate_all's GenerationError); anything else it raises is raised here, as in one
    process.
    """
    p = pool()
    if p is None:
        return None
    try:
        futures = {a: p.submit(fn, **kw) for a, kw in jobs.items()}
    except Exception:  # noqa: BLE001 - e.g. a broken pool
        _broken()
        return None
    out = {}
    for a, f in futures.items():
        try:
            out[a] = f.result()
        except Exception as exc:  # noqa: BLE001
            from concurrent.futures.process import BrokenProcessPool
            if isinstance(exc, (BrokenProcessPool, OSError, EOFError)) or type(exc).__name__ == "PicklingError":
                _broken()
                return None
            raise
    return out
