"""MIDI export (SPEC §7).

Every file: concert pitch, 480 PPQ, 4/4, the app's tempo, starting at bar 1 with no lead-in, one constant CC1
value per part at the start (the part's section Dynamics), and the whole clip length.
  * Per-part files (Milestone 3): one type-0 file per part line (divisi lines are separate files),
    {ProjectName}_{Part}_{Alt}.mid, e.g. NightRise_Vln1-a_A.mid.
  * Full score (Milestone 6): one type-1 file, a tempo track plus one named track per sounding part,
    {ProjectName}_Full_{Alt}.mid.
  * Combined divisi (Milestone 6, optional): one file per instrument that plays on several lines (divisi,
    a2 winds, horns 1-4, melody host), all its lines on one track, {ProjectName}_{Code}-all_{Alt}.mid,
    e.g. NightRise_Hn-all_A.mid. Unisons between its lines are merged so no two notes overlap on one pitch.
"""
from __future__ import annotations

import re
from pathlib import Path

import mido

from .generator import EXPORT_CODE, Orchestration
from .instruments import instruments
from .midi_io import PPQ, Note, write_notes

PARTS, FULL, BOTH = "parts", "full", "both"
EXPORT_CHOICES = (PARTS, FULL, BOTH)

EXPORT_ROOT = Path.home() / "Documents" / "OrchSketch" / "Exports"


def safe_name(text: str) -> str:
    """A file-name-safe version of a project name ("Night Rise!" -> "Night_Rise")."""
    s = re.sub(r"[^A-Za-z0-9_\-]+", "_", text.strip()).strip("_")
    return s or "OrchSketch"


def part_filename(project: str, line_export: str, alt: str) -> str:
    return f"{safe_name(project)}_{line_export}_{alt}.mid"


def export_folder(project: str, root: Path | None = None) -> Path:
    return (root or EXPORT_ROOT) / safe_name(project)


def export_part(orch: Orchestration, line_id: str, folder: Path | str, project: str, tempo: float,
                length: int) -> Path | None:
    """Write one part. Returns the path, or None if the part rests throughout."""
    line = orch.line(line_id)
    part = orch.part(line_id)
    if not part.notes:
        return None
    path = Path(folder) / part_filename(project, line.export, orch.approach)
    return write_notes(path, list(part.notes), tempo, track_name=line.label, length=length,
                       cc1=orch.cc1_for(line_id))


def export_parts(orch: Orchestration, folder: Path | str, project: str, tempo: float, length: int,
                 line_ids: list[str] | None = None) -> list[Path]:
    """Write every part (or the given ones) that has notes. Returns the files written."""
    out = []
    for ln in orch.lines:
        if line_ids is not None and ln.id not in line_ids:
            continue
        p = export_part(orch, ln.id, folder, project, tempo, length)
        if p is not None:
            out.append(p)
    return out


# ---------------------------------------------------------------- full score (type 1)
def full_filename(project: str, alt: str) -> str:
    return f"{safe_name(project)}_Full_{alt}.mid"


def _track_events(notes, channel: int = 0) -> list[tuple[int, int, mido.Message]]:
    events = []
    for n in notes:
        events.append((n.start, 1, mido.Message("note_on", note=n.pitch, velocity=n.velocity, channel=channel)))
        events.append((n.end, 0, mido.Message("note_off", note=n.pitch, velocity=0, channel=channel)))
    events.sort(key=lambda e: (e[0], e[1], e[2].note))  # offs before ons at the same tick
    return events


def _append_timed(track: mido.MidiTrack, events, length: int):
    now = 0
    for tick, _, msg in events:
        track.append(msg.copy(time=tick - now))
        now = tick
    track.append(mido.MetaMessage("end_of_track", time=max(length, now) - now))


def export_full(orch: Orchestration, folder: Path | str, project: str, tempo: float, length: int) -> Path | None:
    """One type-1 file: track 1 holds the name, time signature and tempo; then one named track per
    sounding part (score order) with its CC1 value. Returns None if nothing sounds."""
    lines = [ln for ln in orch.lines if orch.part(ln.id).notes]
    if not lines:
        return None
    path = Path(folder) / full_filename(project, orch.approach)
    path.parent.mkdir(parents=True, exist_ok=True)
    mid = mido.MidiFile(type=1, ticks_per_beat=PPQ)
    head = mido.MidiTrack()
    head.append(mido.MetaMessage("track_name", name=f"{project} {orch.approach}", time=0))
    head.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    head.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo), time=0))
    _append_timed(head, [], length)
    mid.tracks.append(head)
    for ln in lines:
        tr = mido.MidiTrack()
        tr.append(mido.MetaMessage("track_name", name=ln.label, time=0))
        tr.append(mido.Message("control_change", control=1, value=orch.cc1_for(ln.id), channel=0, time=0))
        _append_timed(tr, _track_events(orch.part(ln.id).notes), length)
        mid.tracks.append(tr)
    mid.save(str(path))
    return path


# ---------------------------------------------------------------- combined divisi files
def combined_groups(orch: Orchestration) -> dict[str, list[str]]:
    """Instrument code -> its sounding line ids, for every instrument playing on two or more lines."""
    by_inst: dict[str, list[str]] = {}
    for ln in orch.lines:
        if orch.part(ln.id).notes:
            by_inst.setdefault(ln.instrument, []).append(ln.id)
    return {EXPORT_CODE.get(inst, inst) + "-all": ids for inst, ids in by_inst.items() if len(ids) > 1}


def merge_unisons(notes) -> list[Note]:
    """Several lines on one track: same-pitch notes that overlap or touch become one note (loudest velocity),
    so a track never has two overlapping notes on one pitch."""
    out: list[Note] = []
    for n in sorted(notes, key=lambda n: (n.pitch, n.start, n.end)):
        last = out[-1] if out else None
        if last is not None and last.pitch == n.pitch and n.start < last.end:
            out[-1] = Note(n.pitch, last.start, max(last.end, n.end), max(last.velocity, n.velocity))
        else:
            out.append(n)
    return sorted(out, key=lambda n: (n.start, -n.pitch))


def export_combined(orch: Orchestration, folder: Path | str, project: str, tempo: float, length: int
                    ) -> list[Path]:
    out = []
    for code, ids in combined_groups(orch).items():
        notes = merge_unisons(n for lid in ids for n in orch.part(lid).notes)
        name = _group_label(orch, ids)
        cc1 = max(orch.cc1_for(lid) for lid in ids)
        path = Path(folder) / part_filename(project, code, orch.approach)
        out.append(write_notes(path, notes, tempo, track_name=name, length=length, cc1=cc1))
    return out


def _group_label(orch: Orchestration, ids: list[str]) -> str:
    return instruments()[orch.line(ids[0]).instrument].name + " (all lines)"


# ---------------------------------------------------------------- everything
def export_all(orch: Orchestration, folder: Path | str, project: str, tempo: float, length: int,
               what: str = BOTH, combined: bool = False) -> list[Path]:
    """Export by the window's choice: per-part files, the full score, or both; plus, when ticked, the combined
    divisi files."""
    if what not in EXPORT_CHOICES:
        raise ValueError(f"export choice must be one of {EXPORT_CHOICES}")
    files: list[Path] = []
    if what in (PARTS, BOTH):
        files += export_parts(orch, folder, project, tempo, length)
    if combined:
        files += export_combined(orch, folder, project, tempo, length)
    if what in (FULL, BOTH):
        full = export_full(orch, folder, project, tempo, length)
        if full is not None:
            files.append(full)
    return files
