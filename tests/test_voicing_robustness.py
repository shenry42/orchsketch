"""Every test-set chord must keep its label under many random (seeded) voicings:
spread over octaves, doubled tones, bass in octave 1-3."""
import json
import random
from pathlib import Path

from orchsketch.analysis import label_pitches, parse_symbol
from orchsketch.theory import Key

DATA = Path(__file__).parent / "data"
TRIALS = 60


def test_labels_survive_revoicing():
    rng = random.Random(2026)
    failures = []
    for p in sorted(DATA.glob("*.expected.json")):
        e = json.loads(p.read_text(encoding="utf-8"))
        key = Key(e["key"]["tonic"], e["key"]["mode"])
        for c in e["chords"]:
            lab = parse_symbol(c["label"])
            need = lab.pcs() if lab.bass_in_chord else lab.pcs() - {lab.bass}
            for _ in range(TRIALS):
                bass = rng.choice([24, 36, 48]) + lab.bass % 12
                ups = [rng.choice([48, 60, 72]) + pc for pc in lab.pcs() for _ in range(rng.choice([1, 1, 2]))]
                pitches = sorted({bass} | {u for u in ups if u > bass})
                if not {x % 12 for x in pitches} >= need:
                    continue
                cands = label_pitches(pitches, key, pedal=c.get("pedal", False))
                got = cands[0].label.symbol(key) if cands and cands[0].exact else "?"
                if got != c["label"]:
                    failures.append((p.name[:2], c["label"], got, pitches))
    assert not failures, failures[:10]
