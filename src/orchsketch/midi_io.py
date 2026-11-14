"""Read and write Standard MIDI Files (via mido).

Everything inside the app uses PPQ = 480 ticks per quarter note, whatever the
source file used. Positions start at tick 0 = bar 1, beat 1.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from pathlib import Path

import mido

PPQ = 480
BAR = PPQ * 4  # 4/4 only in v1
GRID = PPQ // 2  # smallest chord grid: 8th note
TOLERANCE = PPQ // 8  # 1/32 note
MAX_BARS = 16


class InputError(Exception):
    """The file can't be used. The message is shown to the user as-is."""


@dataclass(frozen=True)
class Note:
    pitch: int
    start: int  # ticks at PPQ
    end: int
    velocity: int = 100

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass
class Clip:
    notes: list[Note]
    length: int  # ticks, whole bars
    source_ppq: int
    source_path: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def bars(self) -> int:
        return self.length // BAR


def position_text(tick: int) -> str:
    """Tick -> 'bar 2 beat 3' (or 'bar 2 beat 3.5')."""
    bar = tick // BAR + 1
    beat = (tick % BAR) / PPQ + 1
    beat_txt = f"{beat:g}"
    return f"bar {bar} beat {beat_txt}"


# ---------------------------------------------------------------- reading
def _load(path) -> mido.MidiFile:
    try:
        mid = mido.MidiFile(str(path), clip=True)
    except FileNotFoundError:
        raise InputError(f"File not found: {path}")
    except Exception as exc:  # mido raises several types for bad files
        raise InputError(f"This isn't a readable MIDI file ({exc}).")
    if mid.type == 2:
        raise InputError("MIDI type 2 files aren't supported. Export the clip as a normal MIDI file.")
    if not mid.ticks_per_beat or mid.ticks_per_beat <= 0:
        raise InputError("This MIDI file uses SMPTE timing, which isn't supported.")
    return mid


def _raw_notes(mid: mido.MidiFile) -> tuple[list[Note], int, list[str]]:
    """Return notes at PPQ, the latest end-of-track tick at PPQ, and warnings."""
    scale = PPQ / mid.ticks_per_beat
    notes: list[Note] = []
    warnings: list[str] = []
    eot = 0
    tempos = set()
    for track in mid.tracks:
        t = 0
        open_notes: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for msg in track:
            t += msg.time
            if msg.type == "time_signature":
                if (msg.numerator, msg.denominator) != (4, 4):
                    raise InputError(
                        f"The file is in {msg.numerator}/{msg.denominator}. Only 4/4 is supported."
                    )
            elif msg.type == "set_tempo":
                tempos.add(msg.tempo)
            elif msg.type == "note_on" and msg.velocity > 0:
                open_notes.setdefault((msg.channel, msg.note), []).append((t, msg.velocity))
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                stack = open_notes.get((msg.channel, msg.note))
                if stack:
                    start, vel = stack.pop(0)
                    if t > start:
                        notes.append(Note(msg.note, round(start * scale), round(t * scale), vel))
        for (_, pitch), stack in open_notes.items():  # never released: end at track end
            for start, vel in stack:
                if t > start:
                    notes.append(Note(pitch, round(start * scale), round(t * scale), vel))
                    warnings.append("A note had no end; it was ended at the end of the clip.")
        eot = max(eot, round(t * scale))
    if len(tempos) > 1:
        warnings.append("The file has tempo changes; they are ignored (set the tempo in the app).")
    notes.sort(key=lambda n: (n.start, n.pitch))
    return notes, eot, warnings


def _snap_start(tick: int, pitch: int) -> int:
    r = tick % GRID
    if r <= TOLERANCE:
        return tick - r
    if GRID - r <= TOLERANCE:
        return tick + GRID - r
    raise InputError(
        f"A note starts off the 8th-note grid at {position_text(tick)}. "
        "Quantize the chord clip to 1/8 (or finer, on 8th positions) and export again."
    )


def _snap_end(tick: int) -> int:
    """Nearest grid line; exact halves round up so short releases never leave gaps."""
    return int(math.floor(tick / GRID + 0.5)) * GRID


def _clip_length(notes: list[Note], eot: int) -> int:
    last = max((n.end for n in notes), default=0)
    bars = max(1, math.ceil(last / BAR))
    eot_bars = math.ceil(_snap_end(eot) / BAR) if eot else 0
    if bars <= MAX_BARS and bars < eot_bars <= MAX_BARS:
        bars = eot_bars  # keep trailing empty space that was part of the clip
    return bars * BAR


def read_chord_file(path) -> Clip:
    """Read a block-chord clip: snap to the 8th grid and validate it."""
    mid = _load(path)
    raw, eot, warnings = _raw_notes(mid)
    if not raw:
        raise InputError("The file has no notes.")
    snapped: dict[tuple[int, int], Note] = {}
    for n in raw:
        s = _snap_start(n.start, n.pitch)
        e = max(_snap_end(n.end), s + GRID)
        key = (n.pitch, s)
        # The same pitch struck twice at one position: keep the longer one.
        if key not in snapped or snapped[key].end < e:
            snapped[key] = Note(n.pitch, s, e, n.velocity)
    notes = sorted(snapped.values(), key=lambda n: (n.start, n.pitch))
    # Same pitch overlapping itself after snapping: cut the earlier note.
    by_pitch: dict[int, list[Note]] = {}
    for n in notes:
        by_pitch.setdefault(n.pitch, []).append(n)
    fixed: list[Note] = []
    for pitch_notes in by_pitch.values():
        for a, b in zip(pitch_notes, pitch_notes[1:] + [None]):
            if b is not None and a.end > b.start:
                a = replace(a, end=b.start)
            fixed.append(a)
    notes = sorted(fixed, key=lambda n: (n.start, n.pitch))
    last = max(n.end for n in notes)
    if last > MAX_BARS * BAR:
        raise InputError(
            f"The clip is {math.ceil(last / BAR)} bars long. The limit is {MAX_BARS} bars."
        )
    return Clip(notes, _clip_length(notes, eot), mid.ticks_per_beat, str(path), warnings)


def read_monophonic_file(path, label: str = "Melody") -> Clip:
    """Read a melody or bass clip. Rhythm is kept as played (no 8th snapping)."""
    mid = _load(path)
    raw, eot, warnings = _raw_notes(mid)
    if not raw:
        raise InputError(f"The {label.lower()} file has no notes.")
    out: list[Note] = []
    for n in raw:
        if out and n.start - out[-1].start <= TOLERANCE:
            raise InputError(
                f"The {label.lower()} file has two notes at once at {position_text(n.start)}. "
                "It must be one note at a time."
            )
        if out and out[-1].end > n.start:  # legato overlap: trim
            out[-1] = replace(out[-1], end=n.start)
        out.append(n)
    last = max(n.end for n in out)
    if last > MAX_BARS * BAR + TOLERANCE:
        raise InputError(f"The {label.lower()} file is longer than {MAX_BARS} bars.")
    return Clip(out, _clip_length(out, eot), mid.ticks_per_beat, str(path), warnings)


# ---------------------------------------------------------------- writing
def note_events(notes, channel: int = 0, controls=None) -> list:
    """(tick, order, message) for notes and controller events, sorted: note-offs, then controllers, then
    note-ons at the same tick."""
    events = []
    for n in notes:
        events.append((n.start, 2 if controls else 1,
                       mido.Message("note_on", note=n.pitch, velocity=n.velocity, channel=channel)))
        events.append((n.end, 0, mido.Message("note_off", note=n.pitch, velocity=0, channel=channel)))
    if controls:
        for t, cc, v in controls:
            events.append((t, 1, mido.Message("control_change", control=cc, value=v, channel=channel)))
        events.sort(key=lambda e: (e[0], e[1], getattr(e[2], "note", 0), getattr(e[2], "control", 0)))
    else:
        events.sort(key=lambda e: (e[0], e[1], e[2].note))  # offs before ons at the same tick
    return events


def write_notes(
    path,
    notes: list[Note],
    tempo_bpm: float,
    track_name: str = "OrchSketch",
    length: int | None = None,
    program: int | None = None,
    cc1: int | None = None,
    channel: int = 0,
    controls=None,
) -> Path:
    """Write one track as a type-0 MIDI file at PPQ 480, starting at bar 1. controls (v1.4): (tick, controller,
    value) events, e.g. CC1/CC11 curves, sent before the notes at the same tick."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mid = mido.MidiFile(type=0, ticks_per_beat=PPQ)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name=track_name, time=0))
    track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
    if program is not None:
        track.append(mido.Message("program_change", program=program, channel=channel, time=0))
    if cc1 is not None:
        track.append(mido.Message("control_change", control=1, value=cc1, channel=channel, time=0))
    events = note_events(notes, channel, controls)
    now = 0
    for tick, _, msg in events:
        track.append(msg.copy(time=tick - now))
        now = tick
    end = max(length or 0, now)
    track.append(mido.MetaMessage("end_of_track", time=end - now))
    mid.save(str(path))
    return path
