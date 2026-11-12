"""Writes tests/data/a_v03_snapshot.json: a hash of approach A's output per test file, seed and section set.

Run once on v0.3 (Milestone 3). test_generator.py checks that approach A at the default settings
still gives exactly these results, so later milestones can't change A by accident.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from test_generator import COMBOS, EXPECTED, load  # noqa: E402
from orchsketch.generator import Ensemble, generate  # noqa: E402


def digest(orch) -> str:
    rows = [[ln.id, orch.cells[ln.id]] for ln in orch.lines if any(p is not None for p in orch.cells[ln.id])]
    return hashlib.sha1(json.dumps(rows).encode()).hexdigest()[:16]


def runs():
    for exp in EXPECTED:
        chords, key = load(exp)
        name = exp.name.split(".")[0]
        for seed in (1, 2, 3):
            yield f"{name}|full|{seed}", chords, key, seed, None
        for combo in COMBOS:
            yield f"{name}|{'+'.join(sorted(combo))}|7", chords, key, 7, combo


if __name__ == "__main__":
    out = {}
    for rid, chords, key, seed, combo in runs():
        o = generate(chords, key, seed=seed, ensemble=Ensemble(combo) if combo else None)
        out[rid] = digest(o)
    (HERE / "data" / "a_v03_snapshot.json").write_text(json.dumps(out, indent=0, sort_keys=True), encoding="utf-8")
    print(len(out), "runs")
