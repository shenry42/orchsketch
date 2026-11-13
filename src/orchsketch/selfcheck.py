"""`OrchSketch.exe --self-check`: proves a packaged build has everything it needs (Milestone 6).

Checks, in order: the data files (22 instruments, rules, 6 built-in presets), the generator on a short
progression (all three alternatives, checker clean), per-part and full-score export, a project round trip,
then FluidSynth, the SoundFont and the Windows audio output (WASAPI shared mode, the same way the app opens
it), playing a short chord unless `--no-audio`. The report goes to Documents\\OrchSketch\\logs\\self_check.txt
(and to the console when there is one). Returns 0 when everything passes.
"""
from __future__ import annotations

import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

LOG = Path.home() / "Documents" / "OrchSketch" / "logs" / "self_check.txt"


def run(audio: bool = True, log: Path | None = LOG, synth: bool = True) -> tuple[bool, str]:
    from . import __version__
    lines: list[str] = [f"OrchSketch {__version__} self-check  {datetime.now():%Y-%m-%d %H:%M:%S}",
                        f"Python {sys.version.split()[0]} · frozen={bool(getattr(sys, 'frozen', False))} · "
                        f"{sys.executable}"]
    ok = True

    def step(name, fn):
        nonlocal ok
        try:
            detail = fn()
            lines.append(f"PASS  {name}" + (f": {detail}" if detail else ""))
        except Exception as exc:  # noqa: BLE001 - every failure goes in the report
            ok = False
            lines.append(f"FAIL  {name}: {exc!r}")
            lines.append("      " + traceback.format_exc().strip().replace("\n", "\n      "))

    def data():
        from .instruments import DATA_DIR, instruments
        from .presets import builtin_presets
        from .rules import rules
        insts, pres = instruments(), builtin_presets()
        assert len(insts) == 22, f"{len(insts)} instruments"
        assert len(pres) == 6, f"{len(pres)} presets"
        rules()
        return f"{len(insts)} instruments, {len(pres)} presets, rules ({DATA_DIR})"

    state: dict = {}

    def generate():
        from .analysis.chords import ChordLabel
        from .checker import ChordSpan
        from .generator import generate_all
        from .midi_io import BAR
        from .rules import ERROR
        from .theory import Key
        labels = [ChordLabel(9, "min", 9), ChordLabel(5, "maj", 5), ChordLabel(0, "maj", 0), ChordLabel(7, "maj", 7)]
        chords = [ChordSpan(i * BAR, (i + 1) * BAR, lab) for i, lab in enumerate(labels)]
        alts = generate_all(chords, Key("A", "minor"), seed=1)
        from . import parallel
        par = generate_all(chords, Key("A", "minor"), seed=1, parallel=True)
        assert parallel.pool() is not None, "the A/B/C worker processes couldn't start"
        assert par == alts, "A/B/C built in worker processes differ from one process"
        for a, o in alts.items():
            assert not isinstance(o, Exception), f"{a}: {o}"
            assert not [i for i in o.report.issues if i.severity == ERROR], f"{a}: checker errors"
        state["alts"] = alts
        return ", ".join(f"{a} {len(o.sounding_lines)} parts" for a, o in alts.items()) + ", worker processes OK"

    def export():
        from .export import BOTH, export_all
        from .midi_io import BAR
        with tempfile.TemporaryDirectory() as d:
            files = export_all(state["alts"]["A"], d, "SelfCheck", 140, 4 * BAR, BOTH, combined=True)
            assert any(f.name == "SelfCheck_Full_A.mid" for f in files)
            return f"{len(files)} files"

    def project():
        from . import project as pj
        from .midi_io import BAR, Clip, Note
        clip = Clip([Note(57, 0, BAR), Note(60, 0, BAR), Note(64, 0, BAR)], 4 * BAR, 480, "selfcheck.mid")
        alts = state["alts"]
        p = pj.Project(pj.InputFile("selfcheck.mid", b"MThd"), clip, alts=(alts["A"], alts["B"], alts["C"]))
        with tempfile.TemporaryDirectory() as d:
            q = pj.load(pj.save(p, Path(d) / "selfcheck.osk"))
        assert q == p, "the project didn't reopen exactly"
        return "saved and reopened exactly"

    def open_audio():
        from .playback import fluid_env
        from .playback.synth import open_synth
        dll = fluid_env.prepare()
        sf = fluid_env.find_soundfont()
        fs, sfid = open_synth(sf)
        try:
            if audio:
                fs.program_select(0, sfid, 0, 48)
                for p in (57, 60, 64):
                    fs.noteon(0, p, 90)
                time.sleep(1.5)
                for p in (57, 60, 64):
                    fs.noteoff(0, p)
                time.sleep(0.5)
        finally:
            fs.delete()
        return f"DLLs {dll}, SoundFont {sf.name} ({sf.stat().st_size // 2**20} MB), WASAPI shared" + (
            ", played a chord" if audio else "")

    steps = [("Data files", data), ("Generator", generate), ("Export", export), ("Project", project)]
    if synth:
        steps.append(("Audio", open_audio))
    for name, fn in steps:
        step(name, fn)
    lines.append("SELF-CHECK OK" if ok else "SELF-CHECK FAILED")
    text = "\n".join(lines)
    if log is not None:
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(text + "\n", encoding="utf-8")
        except OSError:
            pass
    return ok, text


def main(argv: list[str]) -> int:
    ok, text = run(audio="--no-audio" not in argv)
    if sys.stdout is not None:
        try:
            print(text)
        except OSError:
            pass
    return 0 if ok else 1
