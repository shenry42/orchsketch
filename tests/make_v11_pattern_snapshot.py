"""Writes tests/data/v11_patterns_snapshot.json: a hash of every note of patterned results at v1.1.

The A and v0.4 snapshots cover Sustain only. This one covers what Milestone 7 rebuilt: the six v1 rhythm
patterns (master, per section, per instrument, presets), moderate mode's passing tones, re-strike, per-section
dynamics, and the melody and bass files. It was run once on v1.1 (tag v1.1); tests/test_pattern_engine.py checks
that v1.2 with every new option at its default gives exactly the same notes.
"""
import json
import sys
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

from make_v04_snapshot import note_digest  # noqa: E402
from test_generator import EXPECTED, load  # noqa: E402
from orchsketch.generator import APPROACHES, Ensemble, Settings, generate, rerender  # noqa: E402
from orchsketch.instruments import SECTIONS  # noqa: E402
from orchsketch.midi_io import read_monophonic_file  # noqa: E402
from orchsketch.presets import builtin_presets  # noqa: E402

DATA = HERE / "data"
V1 = ("8ths", "16ths", "16ths_alt", "stabs", "half_time")


def preset_settings(p, **kw):
    ens = Ensemble(instruments=frozenset(p.instruments), forces=p.forces, density=p.density)
    sp = p.section_patterns()
    return Settings(ensemble=ens, section_patterns=sp, instrument_patterns=p.instrument_patterns(), **kw)


def runs():
    """(run id, function returning the orchestration)."""
    epic = next(p for p in builtin_presets() if p.id == "full_epic")
    heavy = next(p for p in builtin_presets() if p.id == "low_heavy")
    for k, exp in enumerate(EXPECTED):
        name = exp.name.split(".")[0]
        data = json.loads(exp.read_text(encoding="utf-8"))
        chords, key = load(exp)
        for a in APPROACHES:
            def base(a=a, chords=chords, key=key, st=None):
                return generate(chords, key, seed=1, approach=a, settings=st)
            for pt in V1:
                yield f"{name}|{a}|{pt}", (lambda base=base, pt=pt: rerender(base(), Settings(pattern=pt)))
            rot = {sec: V1[(k + j) % len(V1)] for j, sec in enumerate(SECTIONS)}
            yield f"{name}|{a}|rotated", (lambda base=base, rot=rot: rerender(
                base(), Settings(section_patterns=rot, section_dynamics={"brass": "ff", "woodwinds": "p"})))
            yield f"{name}|{a}|restrike8", (lambda base=base: rerender(
                base(), Settings(pattern="8ths", restrike_bars=True)))
            for pt in ("8ths", "16ths", "16ths_alt"):
                yield f"{name}|{a}|moderate|{pt}", (lambda base=base, pt=pt: base(st=Settings(
                    character="moderate", pattern=pt)))
            for p in (epic, heavy):
                yield f"{name}|{a}|{p.id}", (lambda base=base, p=p: base(st=preset_settings(p)))
            if data.get("melody_file"):
                mel = tuple(read_monophonic_file(DATA / data["melody_file"]).notes)
                bass = tuple(read_monophonic_file(DATA / data["bass_file"]).notes)
                yield f"{name}|{a}|epic+files", (lambda base=base, mel=mel, bass=bass: base(st=preset_settings(
                    epic, melody=mel, bass=bass)))
                yield f"{name}|{a}|epic+files+moderate", (lambda base=base, mel=mel, bass=bass: base(
                    st=preset_settings(epic, melody=mel, bass=bass, character="moderate")))


if __name__ == "__main__":
    out = {}
    for rid, fn in runs():
        out[rid] = note_digest(fn())
    (DATA / "v11_patterns_snapshot.json").write_text(json.dumps(out, indent=0, sort_keys=True), encoding="utf-8")
    print(len(out), "runs")
