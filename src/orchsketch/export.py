"""Per-part MIDI export (SPEC §7), Milestone 3.

One type-0 file per part line (divisi lines are separate files), concert pitch, 480 PPQ, 4/4, the app's
tempo, starting at bar 1 with no lead-in, and one constant CC1 value at the start.
Name: {ProjectName}_{Part}_{Alt}.mid, e.g. NightRise_Vln1-a_A.mid.
"""
from __future__ import annotations

import re
from pathlib import Path

from .generator import Orchestration
from .midi_io import write_notes

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
    return write_notes(path, list(part.notes), tempo, track_name=line.label, length=length, cc1=orch.cc1)


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
