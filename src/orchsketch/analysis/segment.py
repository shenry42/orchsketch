"""Split a block-chord clip into chord segments and mark pedal tones (SPEC §2, §3)."""
from __future__ import annotations

from dataclasses import dataclass

from ..midi_io import GRID, Clip, Note


@dataclass(frozen=True)
class Segment:
    index: int
    start: int  # ticks
    end: int
    pitches: tuple[int, ...]  # sorted MIDI pitches sounding throughout the segment
    pedal: bool = False  # the bass is a held pedal note

    @property
    def length(self) -> int:
        return self.end - self.start

    @property
    def is_rest(self) -> bool:
        return not self.pitches

    @property
    def bass(self) -> int | None:
        return self.pitches[0] if self.pitches else None


def _sounding(notes: list[Note], t: int) -> tuple[int, ...]:
    return tuple(sorted({n.pitch for n in notes if n.start <= t < n.end}))


def segment_clip(clip: Clip) -> list[Segment]:
    """A new segment starts wherever the set of sounding pitches changes on the 8th grid.

    Notes have already been snapped to the grid (1/32 tolerance) when the clip was read,
    and a chord struck again with exactly the same pitches stays one segment.
    """
    raw: list[tuple[int, int, tuple[int, ...]]] = []
    for t in range(0, clip.length, GRID):
        pitches = _sounding(clip.notes, t)
        if raw and raw[-1][2] == pitches:
            raw[-1] = (raw[-1][0], t + GRID, pitches)
        else:
            raw.append((t, t + GRID, pitches))
    segments = [Segment(i, s, e, p) for i, (s, e, p) in enumerate(raw)]
    return _mark_pedals(segments, clip.notes)


def _mark_pedals(segments: list[Segment], notes: list[Note]) -> list[Segment]:
    """A pedal is one held note that is the lowest sounding note across 2+ chord segments."""
    pedal_idx: set[int] = set()
    for n in notes:
        covered = [s for s in segments if not s.is_rest and n.start <= s.start and s.end <= n.end]
        if len(covered) >= 2 and all(s.bass == n.pitch for s in covered):
            pedal_idx.update(s.index for s in covered)
    return [
        Segment(s.index, s.start, s.end, s.pitches, pedal=s.index in pedal_idx) for s in segments
    ]
