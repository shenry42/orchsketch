"""FROZEN COPY of v1.1 src/orchsketch/patterns.py, kept only so tests can prove the v1.2 data-driven renderer
gives exactly the same notes (tests/test_patterns.py). Do not edit.

Rhythm patterns (SPEC §5c): turn one pitch per part per chord into notes.

Patterns are applied after the voicings are chosen (SPEC §5 step 5), so they never change which pitches a
part plays at a chord change. Every pattern strikes at the start of each chord.

    sustain     the chord's length; a note common to two consecutive identical chords is held (tied)
    8ths        repeated 8ths, accented on beats 1 and 3
    16ths       repeated 16ths, accented on every beat
    16ths_alt   16ths alternating the part's note with the next chord tone below (above if none fits),
                always ending on the part's own note
    stabs       short 8th-note hits on beat 1 and the "and" of 2
    half_time   quarter-note hits on beats 1 and 3

In moderate mode the 8th and 16th ostinatos may end a chord on a diatonic passing tone toward the part's next
note (when the part moves by a 3rd). The generator re-checks every chord and falls back to plain Sustain for a
part at a chord where a pattern would break a rule (see generator._render).
No UI code.
"""
from __future__ import annotations

from orchsketch.midi_io import BAR, PPQ, Note

SUSTAIN, EIGHTHS, SIXTEENTHS, SIXTEENTHS_ALT, STABS, HALF_TIME = (
    "sustain", "8ths", "16ths", "16ths_alt", "stabs", "half_time")
PATTERNS = (SUSTAIN, EIGHTHS, SIXTEENTHS, SIXTEENTHS_ALT, STABS, HALF_TIME)
PATTERN_NAMES = {
    SUSTAIN: "Sustain",
    EIGHTHS: "8th ostinato",
    SIXTEENTHS: "16th ostinato",
    SIXTEENTHS_ALT: "16ths alternating",
    STABS: "Brass stabs",
    HALF_TIME: "Half-time pulse",
}
PATTERN_SHORT = {EIGHTHS: "8ths", SIXTEENTHS: "16ths", SIXTEENTHS_ALT: "16ths alt", STABS: "stabs",
                 HALF_TIME: "half-time"}  # grid row tags
# Patterns a choir can sing (no 16ths, no alternating notes)
CHOIR_PATTERNS = (SUSTAIN, EIGHTHS, STABS, HALF_TIME)
PASSING_PATTERNS = (EIGHTHS, SIXTEENTHS, SIXTEENTHS_ALT)
ACCENT = 0.8  # unaccented notes play at 80% of the part's velocity
EIGHTH, SIXTEENTH = PPQ // 2, PPQ // 4
STAB_HITS = (0, PPQ + EIGHTH)  # beat 1 and the "and" of 2
HALF_HITS = (0, 2 * PPQ)  # beats 1 and 3


def allowed(pattern: str, choir: bool) -> bool:
    return pattern in (CHOIR_PATTERNS if choir else PATTERNS)


def soft(velocity: int) -> int:
    return max(1, round(velocity * ACCENT))


def _grid(start: int, end: int, step: int) -> list[tuple[int, int]]:
    out, t = [], start
    while t < end:
        out.append((t, min(t + step, end)))
        t += step
    return out


def _hits(start: int, end: int, offsets: tuple[int, ...], length: int) -> list[tuple[int, int]]:
    """Hits at these offsets in every bar of the span, plus one at the span's start."""
    times = {start}
    bar = start - start % BAR
    while bar < end:
        times.update(bar + o for o in offsets if start <= bar + o < end)
        bar += BAR
    times = sorted(times)
    return [(t, min(t + length, end, nxt)) for t, nxt in zip(times, times[1:] + [end])]


def passing_pitch(pitch: int, nxt: int | None, scale: set[int]) -> int | None:
    """The diatonic step between two notes a 3rd apart (None if there isn't exactly one)."""
    if nxt is None or abs(nxt - pitch) not in (3, 4):
        return None
    lo, hi = sorted((pitch, nxt))
    steps = [p for p in range(lo + 1, hi) if p % 12 in scale]
    return steps[0] if len(steps) == 1 else None


def render(pattern: str, pitch: int, start: int, end: int, velocity: int, *, alt: int | None = None,
           passing: int | None = None) -> list[Note]:
    """Notes for one part at one chord. `alt`: the second tone of 16ths_alt; `passing`: a passing tone that
    replaces the end of an 8th/16th ostinato (moderate mode)."""
    if pattern == SUSTAIN:
        return [Note(pitch, start, end, velocity)]
    if pattern == EIGHTHS:
        cells = _grid(start, end, EIGHTH)
        accent = {0, 2 * PPQ}
        notes = [Note(pitch, s, e, velocity if s % BAR in accent else soft(velocity)) for s, e in cells]
    elif pattern in (SIXTEENTHS, SIXTEENTHS_ALT):
        cells = _grid(start, end, SIXTEENTH)
        notes = []
        for k, (s, e) in enumerate(cells):
            # alternate on the off 16ths, but always end on the part's own note (so the chord change is
            # exactly as in Sustain)
            p = alt if (pattern == SIXTEENTHS_ALT and alt is not None and k % 2 == 1 and k < len(cells) - 1) else pitch
            notes.append(Note(p, s, e, velocity if s % PPQ == 0 else soft(velocity)))
    elif pattern == STABS:
        return [Note(pitch, s, e, velocity) for s, e in _hits(start, end, STAB_HITS, EIGHTH)]
    elif pattern == HALF_TIME:
        return [Note(pitch, s, e, velocity) for s, e in _hits(start, end, HALF_HITS, PPQ)]
    else:
        raise ValueError(f"unknown pattern {pattern!r}")
    if passing is not None and len(notes) >= 4:
        # the last 8th of the chord (two 16ths) becomes the passing tone
        n_last = 1 if pattern == EIGHTHS else 2
        notes = notes[:-n_last] + [Note(passing, n.start, n.end, soft(velocity)) for n in notes[-n_last:]]
    return notes


def split_at_bars(notes: list[Note]) -> list[Note]:
    """Re-strike every bar: a note that crosses a bar line is cut there and struck again."""
    out = []
    for n in notes:
        s = n.start
        while True:
            nxt = (s // BAR + 1) * BAR
            if nxt >= n.end:
                out.append(Note(n.pitch, s, n.end, n.velocity))
                break
            out.append(Note(n.pitch, s, nxt, n.velocity))
            s = nxt
    return out
