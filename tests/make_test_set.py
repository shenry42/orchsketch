"""Builds the 12-progression test set (SPEC §8) into tests/data/.

Run:  python tests/make_test_set.py
Each test gets NN_name.mid plus NN_name.expected.json. Tests 1, 4 and 11 also get
NN_name.melody.mid and NN_name.bass.mid. The expected labels and Roman numerals
below are written by hand: they are the answer key, not output of the labeller.

The files deliberately vary their format so the reader is exercised:
 - PPQ 96 (tests 1-6) and 480 (7-12)
 - MIDI type 0 and type 1 (tempo/meta track + note track)
 - test 3 is "humanized": starts and ends moved within the 1/32 tolerance
 - test 8 re-strikes the same chord (must stay one segment)
 - test 9 holds a pedal tone under changing chords
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import mido

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from orchsketch.analysis.symbols import parse_symbol  # noqa: E402

DATA = ROOT / "tests" / "data"

# (number, slug, tonic, mode, [(symbol, beats, roman)], options)
TESTS = [
    (1, "epic_staple", "A", "minor",
     [("Am", 4, "i"), ("F", 4, "VI"), ("C", 4, "III"), ("G", 4, "VII")], {"melody_bass": True}),
    (2, "basic_major", "C", "major",
     [("C", 4, "I"), ("G", 4, "V"), ("Am", 4, "vi"), ("F", 4, "IV")], {}),
    (3, "natural_minor", "D", "minor",
     [("Dm", 4, "i"), ("Gm", 4, "iv"), ("Am", 4, "v"), ("Dm", 4, "i")], {"humanize": True}),
    (4, "harmonic_minor_v", "E", "minor",
     [("Em", 4, "i"), ("C", 4, "VI"), ("Am", 4, "iv"), ("B", 4, "V")], {"melody_bass": True}),
    (5, "seventh_chords", "F", "major",
     [("Gm7", 4, "ii7"), ("C7", 4, "V7"), ("Fmaj7", 8, "Imaj7")], {}),
    (6, "inversions", "G", "major",
     [("G", 4, "I"), ("D/F#", 4, "V6"), ("Em", 4, "vi"), ("C/E", 4, "IV6")], {}),
    (7, "sus_chords", "D", "major",
     [("Dsus4", 4, "Isus4"), ("D", 4, "I"), ("Gsus2", 4, "IVsus2"), ("G", 4, "IV")], {}),
    (8, "two_per_bar", "C", "minor",
     [("Cm", 2, "i"), ("Ab", 2, "VI"),
      ("Bb", 2, "VII"), ("Cm", 2, "i"),
      ("Ab", 2.5, "VI"), ("Eb", 1.5, "III"),
      ("Bb", 4, "VII"),
      ("Cm", 1.5, "i"), ("Ab", 2.5, "VI"),
      ("Fm", 2, "iv"), ("G", 2, "V"),
      ("Ab", 3, "VI"), ("Bb", 1, "VII"),
      ("Cm", 2, "i"), ("Cm", 2, "i")], {}),  # last bar: same chord struck twice
    (9, "pedal_tone", "C", "minor",
     [("Cm", 4, "i"), ("Ab/C", 4, "VI6"), ("Bb/C", 4, "VII/C"), ("Cm", 4, "i")], {"pedal": 36}),
    (10, "borrowed", "C", "major",
     [("C", 4, "I"), ("Fm", 4, "iv"), ("Ab", 4, "bVI"), ("G", 4, "V")], {}),
    (11, "sixteen_bars", "A", "minor",
     [("Am", 4, "i"), ("F", 4, "VI"), ("C", 2, "III"), ("G", 2, "VII"), ("Am", 4, "i"),
      ("Dm/F", 4, "iv6"), ("E7", 4, "V7"), ("F", 2, "VI"), ("G", 2, "VII"), ("Am", 4, "i"),
      ("Dm", 2, "iv"), ("Dm/F", 2, "iv6"), ("E", 2, "V"), ("E7", 2, "V7"),
      ("Am", 3, "i"), ("G", 1, "VII"), ("F", 4, "VI"),
      ("Dm7", 2, "iv7"), ("E7", 2, "V7"), ("Am", 1.5, "i"), ("F", 2.5, "VI"),
      ("Bm7b5", 2, "iiø7"), ("E7", 2, "V7"), ("Am", 4, "i")], {"melody_bass": True}),
    (12, "power_and_ambiguous", "A", "minor",
     [("A5", 4, "i5"), ("F5", 4, "VI5"), ("C5", 4, "III5"), ("G5", 4, "VII5"),
      ("Am7", 4, "i7"), ("C6", 4, "IIIadd6"), ("Bm7b5", 4, "iiø7")], {}),
]

# Ambiguous chords: these labels must appear among the alternatives too.
MUST_BE_ALTERNATIVE = {
    (12, 4): ["C6/A"],  # Am7 (A bass) also reads as C6 over A
    (12, 5): ["Am7/C"],  # C6 (C bass) also reads as Am7 over C
}

UPPER_FLOOR = 55  # G3: upper voices are stacked in close position from here up
BASS_BASE = 36  # C2: bass notes go in C2..B2


def voicing(symbol: str) -> tuple[int, list[int]]:
    """Bass pitch + close-position upper voices for a symbol."""
    label = parse_symbol(symbol)
    bass = BASS_BASE + label.bass % 12
    upper = []
    for pc in sorted(label.pcs(), key=lambda pc: (pc - UPPER_FLOOR) % 12):
        upper.append(UPPER_FLOOR + (pc - UPPER_FLOOR) % 12)
    return bass, sorted(upper)


def _write(path: Path, notes: list[tuple[int, float, float, int]], ppq: int, mtype: int, tempo=140):
    """notes: (pitch, start_beat, end_beat, velocity). Positions may be fractional ticks."""
    mid = mido.MidiFile(type=mtype, ticks_per_beat=ppq)
    meta = [
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0),
        mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo), time=0),
    ]
    events = []
    for pitch, s, e, vel in notes:
        events.append((round(s * ppq), 1, mido.Message("note_on", note=pitch, velocity=vel)))
        events.append((round(e * ppq), 0, mido.Message("note_off", note=pitch, velocity=0)))
    events.sort(key=lambda x: (x[0], x[1], x[2].note))
    note_track = mido.MidiTrack()
    now = 0
    for tick, _, msg in events:
        note_track.append(msg.copy(time=tick - now))
        now = tick
    if mtype == 0:
        mid.tracks.append(mido.MidiTrack(meta + list(note_track)))
    else:
        mid.tracks.append(mido.MidiTrack(meta))
        note_track.insert(0, mido.MetaMessage("track_name", name=path.stem, time=0))
        mid.tracks.append(note_track)
    mid.save(str(path))


def build(num, slug, tonic, mode, prog, opts):
    rng = random.Random(num)
    ppq = 96 if num <= 6 else 480
    mtype = 0 if num % 2 else 1
    base = DATA / f"{num:02d}_{slug}"
    notes = []
    t = 0.0
    total = sum(b for _, b, _ in prog)
    pedal = opts.get("pedal")
    for symbol, beats, _ in prog:
        bass, upper = voicing(symbol)
        voices = upper if pedal else [bass] + upper
        if pedal and parse_symbol(symbol).root % 12 == pedal % 12 and 60 + pedal % 12 not in voices:
            voices = sorted(voices + [60 + pedal % 12])
        for p in voices:
            s, e = t, t + beats
            if opts.get("humanize"):
                s = max(0.0, s + rng.uniform(-0.08, 0.08))  # within 1/32 = 0.125 beat
                e = e - rng.uniform(0.0, 0.1)
            notes.append((p, s, e, 96))
        t += beats
    if pedal:
        notes.append((pedal, 0.0, total, 96))
    _write(base.with_suffix(".mid"), notes, ppq, mtype)

    # expected labels: consecutive identical symbols merge into one segment
    chords = []
    t = 0.0
    for symbol, beats, roman in prog:
        if chords and chords[-1]["label"] == symbol and not pedal:
            chords[-1]["beats"] += beats
        else:
            chords.append({"start_beat": t, "beats": beats, "label": symbol, "roman": roman})
        t += beats
    for (n, idx), alts in MUST_BE_ALTERNATIVE.items():
        if n == num:
            chords[idx]["also_in_alternatives"] = alts
    if pedal:
        for c in chords:
            c["pedal"] = True
    expected = {"test": num, "file": base.with_suffix(".mid").name, "key": {"tonic": tonic, "mode": mode},
                "bars": int(total // 4), "chords": chords}
    if opts.get("melody_bass"):
        expected["melody_file"] = base.name + ".melody.mid"
        expected["bass_file"] = base.name + ".bass.mid"
        _melody_and_bass(base, prog, ppq, mtype)
    base.with_suffix(".expected.json").write_text(json.dumps(expected, indent=2, ensure_ascii=False) + "\n",
                                                  encoding="utf-8")


def _melody_and_bass(base: Path, prog, ppq: int, mtype: int):
    """Simple monophonic lines: bass on the chord's bass note, melody on chord tones (octave 5)."""
    bass_notes, mel_notes = [], []
    t = 0.0
    for symbol, beats, _ in prog:
        label = parse_symbol(symbol)
        b = BASS_BASE + label.bass % 12
        step = 2.0 if beats >= 2 else beats
        x = 0.0
        while x < beats - 1e-9:
            d = min(step, beats - x)
            bass_notes.append((b, t + x, t + x + d * 0.95, 100))
            x += d
        tones = sorted(72 + (pc - 72) % 12 for pc in label.pcs())  # C5 and up
        x, i = 0.0, 0
        while x < beats - 1e-9:
            d = min(1.0, beats - x)
            mel_notes.append((tones[i % len(tones)], t + x, t + x + d, 90))
            x += d
            i += 1
        t += beats
    _write(Path(str(base) + ".bass.mid"), bass_notes, ppq, mtype)
    _write(Path(str(base) + ".melody.mid"), mel_notes, ppq, mtype)


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    for spec in TESTS:
        build(*spec)
    print(f"Wrote {len(TESTS)} tests to {DATA}")


if __name__ == "__main__":
    main()
