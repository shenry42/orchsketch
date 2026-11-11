"""Audition player (SPEC §6): plays an orchestration through FluidSynth with loop, tempo, mute and solo.

The timing logic is plain Python (`Sequence`), so it is tested without audio. `Player` drives it from a
Qt timer and talks to a backend (FluidSynth in the app, a fake in tests).

General MIDI has 16 channels (channel 10 is drums), so parts share a channel per GM program. Mute and
solo work per part by filtering notes, and a reference count per (channel, pitch) keeps unison
doublings on one program from cutting each other off.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from ..midi_io import PPQ

DRUM_CHANNEL = 9
MAX_CHANNELS = 15


@dataclass(frozen=True)
class Event:
    tick: int
    on: bool
    part: str
    pitch: int
    velocity: int


class Backend:
    """What the player needs from a synth."""

    def program(self, channel: int, program: int): ...
    def noteon(self, channel: int, pitch: int, velocity: int): ...
    def noteoff(self, channel: int, pitch: int): ...
    def close(self): ...


class FluidBackend(Backend):
    def __init__(self):
        from .synth import open_synth  # noqa: PLC0415  (only when audio is actually needed)
        self.fs, self.sfid = open_synth()

    def program(self, channel, program):
        self.fs.program_select(channel, self.sfid, 0, program)

    def noteon(self, channel, pitch, velocity):
        self.fs.noteon(channel, pitch, velocity)

    def noteoff(self, channel, pitch):
        self.fs.noteoff(channel, pitch)

    def close(self):
        self.fs.delete()


def channel_map(programs: list[int]) -> dict[int, int]:
    """GM program -> MIDI channel (0-based), skipping the drum channel. Extra programs share the last."""
    out: dict[int, int] = {}
    free = [c for c in range(16) if c != DRUM_CHANNEL]
    for prog in programs:
        if prog not in out:
            out[prog] = free[min(len(out), MAX_CHANNELS - 1)]
    return out


class Sequence:
    """Note events for a set of parts, with mute/solo, sent to a backend as time advances."""

    def __init__(self, backend: Backend, parts: list[tuple[str, int, list]], length: int,
                 sections: dict[str, str] | None = None):
        """parts: (part id, GM program, notes). sections: part id -> section name (for section solo)."""
        self.backend = backend
        self.length = length
        self.sections = sections or {}
        progs = [prog for _, prog, _ in parts]
        self.channels = channel_map(progs)
        self.part_channel = {pid: self.channels[prog] for pid, prog, _ in parts}
        for prog, ch in self.channels.items():
            backend.program(ch, prog)
        ev = []
        for pid, _, notes in parts:
            for n in notes:
                if n.start < length:
                    ev.append(Event(n.start, True, pid, n.pitch, n.velocity))
                    ev.append(Event(min(n.end, length), False, pid, n.pitch, 0))
        ev.sort(key=lambda e: (e.tick, e.on, e.part, e.pitch))  # offs before ons at the same tick
        self.events = ev
        self.muted: set[str] = set()
        self.soloed: set[str] = set()
        self.pos = 0  # tick
        self._i = 0  # next event index
        self._sounding: dict[str, set[int]] = {}  # part -> pitches it holds on
        self._refs: dict[tuple[int, int], int] = {}

    # --- mute / solo
    def audible(self, part: str) -> bool:
        if self.soloed:
            return part in self.soloed and part not in self.muted
        return part not in self.muted

    def set_mute(self, part: str, on: bool):
        (self.muted.add if on else self.muted.discard)(part)
        self._silence_inaudible()

    def set_solo(self, part: str, on: bool):
        (self.soloed.add if on else self.soloed.discard)(part)
        self._silence_inaudible()

    def set_section(self, section: str, *, mute: bool | None = None, solo: bool | None = None):
        for pid, sec in self.sections.items():
            if sec == section:
                if mute is not None:
                    (self.muted.add if mute else self.muted.discard)(pid)
                if solo is not None:
                    (self.soloed.add if solo else self.soloed.discard)(pid)
        self._silence_inaudible()

    # --- note output
    def _on(self, part, pitch, vel):
        ch = self.part_channel[part]
        held = self._sounding.setdefault(part, set())
        if pitch in held:
            return
        held.add(pitch)
        k = (ch, pitch)
        self._refs[k] = self._refs.get(k, 0) + 1
        if self._refs[k] == 1:
            self.backend.noteon(ch, pitch, vel)

    def _off(self, part, pitch):
        held = self._sounding.get(part, set())
        if pitch not in held:
            return
        held.discard(pitch)
        ch = self.part_channel[part]
        k = (ch, pitch)
        self._refs[k] -= 1
        if self._refs[k] == 0:
            del self._refs[k]
            self.backend.noteoff(ch, pitch)

    def _silence_inaudible(self):
        for part in list(self._sounding):
            if not self.audible(part):
                for p in list(self._sounding[part]):
                    self._off(part, p)

    def all_off(self):
        for part in list(self._sounding):
            for p in list(self._sounding[part]):
                self._off(part, p)

    # --- time
    def advance_to(self, tick: int):
        """Send every event up to (not including) `tick`."""
        while self._i < len(self.events) and self.events[self._i].tick < tick:
            e = self.events[self._i]
            self._i += 1
            if e.on:
                if self.audible(e.part):
                    self._on(e.part, e.pitch, e.velocity)
            else:
                self._off(e.part, e.pitch)
        self.pos = tick

    def seek(self, tick: int = 0):
        self.all_off()
        self.pos = tick
        self._i = 0
        while self._i < len(self.events) and self.events[self._i].tick < tick:
            self._i += 1

    def sounding(self) -> dict[str, set[int]]:
        return {k: set(v) for k, v in self._sounding.items() if v}


class Clock:
    """Wall-clock tick position at a tempo; tempo changes keep the current position."""

    def __init__(self, bpm: float, now=time.perf_counter):
        self.now = now
        self.bpm = bpm
        self._t0 = now()
        self._tick0 = 0.0

    def tick(self) -> float:
        return self._tick0 + (self.now() - self._t0) * self.bpm / 60.0 * PPQ

    def set_bpm(self, bpm: float):
        self._tick0 = self.tick()
        self._t0 = self.now()
        self.bpm = bpm

    def reset(self, tick: float = 0.0):
        self._tick0 = tick
        self._t0 = self.now()


class Player:
    """Plays a Sequence in real time from a Qt timer. Call play()/stop(); loop and tempo are live."""

    INTERVAL_MS = 5

    def __init__(self, backend_factory=FluidBackend):
        self.backend_factory = backend_factory
        self.backend: Backend | None = None
        self.seq: Sequence | None = None
        self.loop = True
        self.bpm = 140.0
        self.clock: Clock | None = None
        self.timer = None
        self.on_stopped = None  # callback when playback reaches the end without loop

    def ensure_backend(self) -> Backend:
        if self.backend is None:
            self.backend = self.backend_factory()
        return self.backend

    def load(self, parts, length, sections=None):
        was = self.playing
        self.stop()
        self.seq = Sequence(self.ensure_backend(), parts, length, sections)
        if was:
            self.play()

    @property
    def playing(self) -> bool:
        return self.timer is not None and self.timer.isActive()

    def play(self):
        if self.seq is None:
            return
        from PySide6.QtCore import QTimer  # noqa: PLC0415
        if self.timer is None:
            self.timer = QTimer()
            self.timer.setInterval(self.INTERVAL_MS)
            self.timer.timeout.connect(self._tick)
        self.seq.seek(0)
        self.clock = Clock(self.bpm)
        self.timer.start()

    def stop(self):
        if self.timer is not None:
            self.timer.stop()
        if self.seq is not None:
            self.seq.all_off()

    def set_bpm(self, bpm: float):
        self.bpm = bpm
        if self.clock is not None:
            self.clock.set_bpm(bpm)

    def _tick(self):
        seq = self.seq
        t = int(self.clock.tick())
        if t >= seq.length:
            seq.advance_to(seq.length + 1)
            if self.loop:
                seq.seek(0)
                self.clock.reset(t - seq.length if t - seq.length < seq.length else 0)
                seq.advance_to(int(self.clock.tick()))
            else:
                self.stop()
                if self.on_stopped:
                    self.on_stopped()
            return
        seq.advance_to(t + 1)

    def close(self):
        self.stop()
        if self.backend is not None:
            self.backend.close()
            self.backend = None
