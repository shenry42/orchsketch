"""Writes tests/data/v04_snapshot.json: a hash of every note (pitch, start, end, velocity) of approaches A, B and C
per test file and preset, plus the Forces x Density samples, at Milestone 4 (v0.4).

Run once on v0.4. test_generator.py checks that Milestone 5's defaults (Sustain everywhere, safe mode, no melody
or bass file, every section on the same slider values) still give exactly these notes, so the new features can't
change v0.4's results by accident.
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from test_generator import EXPECTED, SLIDER_SAMPLE, load  # noqa: E402
from orchsketch.generator import APPROACHES, Ensemble, generate  # noqa: E402
from orchsketch.presets import builtin_presets  # noqa: E402


def note_digest(orch) -> str:
    rows = [[p.id, [[n.pitch, n.start, n.end, n.velocity] for n in p.notes]] for p in orch.parts if p.notes]
    return hashlib.sha1(json.dumps(rows).encode()).hexdigest()[:16]


def runs(slider_approaches=APPROACHES):
    """(run id, chords, key, approach, ensemble or None). Presets use the v0.4 instrument list only.
    The Forces x Density samples are run for `slider_approaches` (the test uses A only, to save time)."""
    for exp in EXPECTED:
        chords, key = load(exp)
        name = exp.name.split(".")[0]
        for a in APPROACHES:
            yield f"{name}|{a}|default", chords, key, a, None
            for p in builtin_presets():
                yield (f"{name}|{a}|{p.id}", chords, key, a,
                       Ensemble(instruments=frozenset(p.instruments), forces=p.forces, density=p.density))
            for forces, density in (SLIDER_SAMPLE if a in slider_approaches else ()):
                yield f"{name}|{a}|{forces}{density}", chords, key, a, Ensemble(forces=forces, density=density)


if __name__ == "__main__":
    out = {}
    for rid, chords, key, a, ens in runs():
        out[rid] = note_digest(generate(chords, key, seed=1, approach=a, ensemble=ens))
    (HERE / "data" / "v04_snapshot.json").write_text(json.dumps(out, indent=0, sort_keys=True), encoding="utf-8")
    print(len(out), "runs")
