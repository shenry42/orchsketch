"""Make tests/data/v13_export_snapshot.json: the exported MIDI files of v1.3 (made on tag v1.3), byte for byte.

Milestone 9 (v1.4) adds CC curves, tremolo and riser parts and humanize to the export. With every new option at
its default the export must stay exactly v1.3's: tests/test_expression.py re-exports these runs and compares
the SHA-256 of every file (parts, full score and combined divisi files).

Run from the repo root:  python tests/make_v13_export_snapshot.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

OUT = HERE / "data" / "v13_export_snapshot.json"

# (test index into EXPECTED, approach, with files, settings overrides): v1.3 features across the export paths
RUNS = [
    (0, "A", False, {}),
    (0, "B", True, {}),
    (0, "C", True, {"pattern": "8ths_rise", "accent": "3+3+2", "pattern_emphasis": True}),
    (3, "B", True, {"shape": "build_hit", "fill": "run"}),
    (3, "A", False, {"shape": "pulse_bed", "section_patterns": (("strings", "8ths"),)}),
    (7, "B", False, {"shape": "drop", "restrike_bars": True}),
    (10, "B", True, {"section_patterns": (("strings", "16ths_pendulum"),), "note_mode": "hybrid"}),
    (10, "C", False, {"theme": True, "shape": "phrase4", "fill": "pickup"}),
    (11, "B", False, {"section_patterns": (("strings", "arp_r5810"), ("brass", "stabs_push"))}),
]


def snapshot_runs():
    from test_textures import EPIC, files
    from test_generator import EXPECTED, load_with_voicings

    from orchsketch.generator import Settings, generate

    out = []
    for k, a, with_files, over in RUNS:
        chords, key, voic = load_with_voicings(EXPECTED[k])
        mel, bass = files(k) if with_files else (None, None)
        pats = dict(EPIC.patterns)
        kw = dict(section_patterns=tuple((s, p) for s, p in pats.items() if s in ("strings", "brass", "woodwinds",
                                                                                   "choir")),
                  instrument_patterns=tuple((s, p) for s, p in pats.items()
                                            if s not in ("strings", "brass", "woodwinds", "choir")))
        kw.update(over)
        theme = kw.pop("theme", False)
        st = Settings(EPIC.ensemble(), tops=tuple(max(v) for v in voic), melody=mel, bass=bass, theme=theme, **kw)
        orch = generate(chords, key, seed=1, approach=a, settings=st)
        name = f"{EXPECTED[k].name.split('.')[0]}_{a}{'_files' if with_files else ''}"
        out.append((name, orch, max(c.end for c in chords)))
    return out


def export_hashes(orch, length: int) -> dict[str, str]:
    from orchsketch.export import BOTH, export_all
    with tempfile.TemporaryDirectory() as tmp:
        files = export_all(orch, Path(tmp), "Snap", 140, length, BOTH, combined=True)
        return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(files)}


def main():
    data = {name: export_hashes(orch, length) for name, orch, length in snapshot_runs()}
    OUT.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({sum(len(v) for v in data.values())} files in {len(data)} runs)")


if __name__ == "__main__":
    main()
