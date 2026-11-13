"""Projects (SPEC §7): save and reopen everything as a JSON `.osk` file. No UI code.

A project holds the input files (embedded copies: the original bytes plus the notes as read), key, tempo,
chord corrections, every setting (sliders per section, patterns per section / instrument / part, melody and
bass options), locks, the chosen alternative, the seed, and each alternative's finished orchestration
(v1.2: also its pattern alternatives 2 and 3) *itself*: rendered notes, cells, meta (swaps, earlier variations, rhythm figures) and checker report.
Reopening rebuilds those objects field by field and never regenerates, so the saved notes come back exactly,
even after an app update changes the generator. The seed is only used when you choose to regenerate.

Encoding: plain JSON. Tuples, sets and the app's own dataclasses are tagged ({"__t": [...]},
{"__c": "Note", "f": {...}}) so every value comes back with its exact type and compares equal. Unknown
fields in a file are skipped and missing ones take their defaults, so later versions can still read old
projects. A value of a type that isn't registered here can't be saved (TypeError): add it to `_CLASSES`.
"""
from __future__ import annotations

import base64
import dataclasses
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__
from .analysis.chords import ChordLabel
from .analysis.segment import Segment
from .checker import ChordSpan, Issue, Part, Report
from .generator import Ensemble, Line, Orchestration, Settings
from .midi_io import Clip, Note
from .theory import Key

FORMAT = "orchsketch-project"
FORMAT_VERSION = 1
SUFFIX = ".osk"
PROJECTS_ROOT = Path.home() / "Documents" / "OrchSketch" / "Projects"

_CLASSES = {c.__name__: c for c in (Orchestration, Line, Part, Note, ChordSpan, ChordLabel, Key, Report, Issue,
                                    Settings, Ensemble, Clip, Segment)}


class ProjectError(Exception):
    """The project can't be read. The message is shown to the user as-is."""


# ---------------------------------------------------------------- generic encoding
def encode(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, bytes):
        return {"__b": base64.b64encode(obj).decode("ascii")}
    if isinstance(obj, list):
        return [encode(x) for x in obj]
    if isinstance(obj, tuple):
        return {"__t": [encode(x) for x in obj]}
    if isinstance(obj, (set, frozenset)):
        items = sorted((encode(x) for x in obj), key=lambda v: json.dumps(v, sort_keys=True))
        return {"__fs" if isinstance(obj, frozenset) else "__s": items}
    if isinstance(obj, dict):
        if all(isinstance(k, str) and not k.startswith("__") for k in obj):
            return {k: encode(v) for k, v in obj.items()}
        return {"__dk": [[encode(k), encode(v)] for k, v in obj.items()]}
    if dataclasses.is_dataclass(obj) and type(obj).__name__ in _CLASSES and _CLASSES[type(obj).__name__] is type(obj):
        return {"__c": type(obj).__name__,
                "f": {f.name: encode(getattr(obj, f.name)) for f in dataclasses.fields(obj) if f.init}}
    raise TypeError(f"can't save a {type(obj).__name__} in a project")


def decode(data: Any) -> Any:
    if isinstance(data, list):
        return [decode(x) for x in data]
    if not isinstance(data, dict):
        return data
    if "__t" in data:
        return tuple(decode(x) for x in data["__t"])
    if "__s" in data:
        return {decode(x) for x in data["__s"]}
    if "__fs" in data:
        return frozenset(decode(x) for x in data["__fs"])
    if "__b" in data:
        return base64.b64decode(data["__b"])
    if "__dk" in data:
        return {decode(k): decode(v) for k, v in data["__dk"]}
    if "__c" in data:
        cls = _CLASSES.get(data["__c"])
        if cls is None:
            raise ProjectError(f"This project uses something this version doesn't know ({data['__c']}).")
        names = {f.name for f in dataclasses.fields(cls) if f.init}
        return cls(**{k: decode(v) for k, v in data["f"].items() if k in names})
    return {k: decode(v) for k, v in data.items()}


# ---------------------------------------------------------------- the project
@dataclass
class InputFile:
    """An embedded input file: its name, original bytes and the notes as read."""
    name: str
    data: bytes = b""
    notes: tuple[Note, ...] = ()


@dataclass
class Project:
    """Everything the window can edit, plus the input files. Field names match the window's EditState."""
    chords: InputFile
    clip: Clip
    tempo: float = 140.0
    loop: bool = True
    labels: tuple = ()  # per segment: (correction ChordLabel or None, confirmed)
    tonic: str = "A"
    mode: str = "minor"
    preset: str = "full_epic"
    active: frozenset = frozenset()
    values: tuple = ()  # per-section sliders and patterns: (section, key, value) triples
    ipatterns: tuple = ()
    ppatterns: tuple = ()
    restrike: bool = False
    melody: InputFile | None = None
    bass: InputFile | None = None
    mel_inst: str | None = None
    mel_double: str = "auto"
    independent: bool = False
    top_voice: str = "smooth"
    keep: bool = False
    seed: int = 1
    alts: tuple = (None, None, None)  # Orchestration, error message or None, for A, B, C
    locks: tuple = (frozenset(), frozenset(), frozenset())
    tab: int = 0
    dirty: bool = False
    scope: str = "all"
    palts: tuple = ((None, None, None),) * 3  # v1.2: per harmony alternative, patterns 2 and 3 (index 1, 2)
    ptabs: tuple = (0, 0, 0)  # v1.2: the pattern alternative shown per harmony alternative
    extra: dict = field(default_factory=dict)  # room for later versions


def to_json(project: Project) -> dict:
    body = {f.name: getattr(project, f.name) for f in dataclasses.fields(project)}
    for k in ("chords", "melody", "bass"):
        v = body[k]
        body[k] = None if v is None else {"name": v.name, "data": base64.b64encode(v.data).decode("ascii"),
                                          "notes": encode(v.notes)}
    for k in list(body):
        if k not in ("chords", "melody", "bass"):
            body[k] = encode(body[k])
    return {"format": FORMAT, "format_version": FORMAT_VERSION, "app_version": __version__,
            "saved": datetime.now().isoformat(timespec="seconds"), "project": body}


def from_json(doc: dict) -> Project:
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ProjectError("This isn't an OrchSketch project file.")
    if doc.get("format_version", 0) > FORMAT_VERSION:
        raise ProjectError(f"This project was saved by a newer OrchSketch ({doc.get('app_version')}). "
                           "Update the app to open it.")
    body = doc["project"]
    names = {f.name for f in dataclasses.fields(Project)}
    kw = {}
    for k, v in body.items():
        if k not in names:
            continue
        if k in ("chords", "melody", "bass"):
            kw[k] = None if v is None else InputFile(v["name"], base64.b64decode(v.get("data", "")),
                                                     tuple(decode(v.get("notes")) or ()))
        else:
            kw[k] = decode(v)
    if "chords" not in kw or "clip" not in kw:
        raise ProjectError("The project has no chord file.")
    try:
        return Project(**kw)
    except (TypeError, ValueError) as exc:
        raise ProjectError(f"The project file is damaged ({exc}).") from None


def save(project: Project, path: Path | str) -> Path:
    path = Path(path)
    if path.suffix.lower() != SUFFIX:
        path = path.with_suffix(SUFFIX)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(to_json(project), separators=(",", ":"))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)  # never leaves a half-written project behind
    return path


def load(path: Path | str) -> Project:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProjectError(f"Couldn't read the project ({exc}).") from None
    except ValueError:
        raise ProjectError("This isn't an OrchSketch project file (it isn't valid JSON).") from None
    return from_json(doc)


def project_name(path: Path | str | None, fallback: str) -> str:
    return Path(path).stem if path else fallback
