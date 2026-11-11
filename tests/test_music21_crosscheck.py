"""Cross-check our chord roots against music21 (SPEC §9). Skipped where music21 isn't installed."""
import json
from pathlib import Path

import pytest

music21 = pytest.importorskip("music21")

from orchsketch.analysis import AnalysisSession  # noqa: E402
from orchsketch.midi_io import read_chord_file  # noqa: E402
from orchsketch.theory import Key  # noqa: E402

DATA = Path(__file__).parent / "data"
# music21 picks a different (equally valid) root for these by design: sus chords, power
# chords, added-6th/minor-7th twins and upper structures over a pedal.
SKIP_QUALITIES = {"sus2", "sus4", "5", "6", "m6"}


@pytest.mark.parametrize("exp_path", sorted(DATA.glob("*.expected.json")), ids=lambda p: p.name[:2])
def test_roots_agree_with_music21(exp_path):
    exp = json.loads(exp_path.read_text(encoding="utf-8"))
    key = Key(exp["key"]["tonic"], exp["key"]["mode"])
    s = AnalysisSession(read_chord_file(DATA / exp["file"]), key)
    checked = 0
    for r in s.chord_results:
        lab = r.label
        if lab.quality in SKIP_QUALITIES or not lab.bass_in_chord:
            continue
        ch = music21.chord.Chord(list(r.segment.pitches))
        assert ch.root().pitchClass == lab.root, f"{lab.symbol(key)} vs music21 root {ch.root().name}"
        checked += 1
    assert checked or exp["test"] in (7, 12)
