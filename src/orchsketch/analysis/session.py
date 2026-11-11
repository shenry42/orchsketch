"""Holds the analysis of one chord clip plus the user's confirmations and corrections.

Generation (from Milestone 3) only ever reads `confirmed_label()`.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..midi_io import Clip
from ..theory import Key
from .chords import Candidate, ChordLabel, label_pitches
from .segment import Segment, segment_clip

AUTO, CONFIRMED, CORRECTED = "auto", "confirmed", "corrected"


@dataclass
class SegmentResult:
    segment: Segment
    candidates: list[Candidate]
    correction: ChordLabel | None = None
    confirmed: bool = False

    @property
    def recognized(self) -> bool:
        return bool(self.candidates) and self.candidates[0].exact

    @property
    def best(self) -> ChordLabel | None:
        return self.candidates[0].label if self.recognized else None

    @property
    def alternatives(self) -> list[ChordLabel]:
        start = 1 if self.recognized else 0
        return [c.label for c in self.candidates[start:]]

    @property
    def label(self) -> ChordLabel | None:
        """What the app currently shows: the correction, else the best guess."""
        return self.correction or self.best

    @property
    def status(self) -> str:
        if self.correction is not None:
            return CORRECTED
        return CONFIRMED if self.confirmed else AUTO


class AnalysisSession:
    def __init__(self, clip: Clip, key: Key):
        self.clip = clip
        self.key = key
        self.segments = segment_clip(clip)
        self.results: list[SegmentResult] = []
        self._label_all()

    def _label_all(self):
        old = {r.segment.index: r for r in self.results}
        self.results = []
        for seg in self.segments:
            cands = [] if seg.is_rest else label_pitches(seg.pitches, self.key, pedal=seg.pedal)
            prev = old.get(seg.index)
            self.results.append(
                SegmentResult(seg, cands, prev.correction if prev else None, prev.confirmed if prev else False)
            )

    # --- user actions ---------------------------------------------------
    def set_key(self, key: Key):
        """Re-label for a new key. Corrections are kept; auto confirmations are cleared."""
        self.key = key
        self._label_all()
        for r in self.results:
            if r.correction is None:
                r.confirmed = False

    def correct(self, index: int, label: ChordLabel):
        r = self.results[index]
        if r.best is not None and label == r.best:
            r.correction, r.confirmed = None, True
        else:
            r.correction, r.confirmed = label, True

    def confirm(self, index: int):
        r = self.results[index]
        if r.label is None:
            raise ValueError("An unrecognized chord must be set by hand before it can be confirmed.")
        r.confirmed = True

    def confirm_all(self) -> int:
        """Confirm every chord that has a label. Returns how many still need setting by hand."""
        unset = 0
        for r in self.results:
            if r.segment.is_rest:
                continue
            if r.label is None:
                unset += 1
            else:
                r.confirmed = True
        return unset

    def revert(self, index: int):
        r = self.results[index]
        r.correction, r.confirmed = None, False

    # --- queries ----------------------------------------------------------
    def confirmed_label(self, index: int) -> ChordLabel | None:
        r = self.results[index]
        return r.label if r.confirmed else None

    @property
    def chord_results(self) -> list[SegmentResult]:
        return [r for r in self.results if not r.segment.is_rest]

    @property
    def all_confirmed(self) -> bool:
        return all(r.confirmed for r in self.chord_results)

    def corrections_dict(self) -> dict:
        """Serializable corrections, for the project file (Milestone 6)."""
        return {
            str(r.segment.index): {"root": r.correction.root, "quality": r.correction.quality,
                                   "bass": r.correction.bass}
            for r in self.results if r.correction is not None
        }
