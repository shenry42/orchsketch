r"""SPEC §7-8 full test-set pass (Milestone 6). Run scripts\\test_set.bat.

For each of the 12 textbook progressions (and tests 1, 4 and 11 again with their melody and bass files) this
drives the real app window off-screen exactly as you would: open the chord file, set the key, Confirm all,
load the melody/bass files, Generate with the default preset (Full epic) at seed 1, and Save the project.
The 15 projects land in Documents\\OrchSketch\\Projects\\TestSet\\ for the ear test: open each one in the app
and listen to A, B and C.

With --benchmark it does the same for the second benchmark (SPEC §8): your own progressions in
tests\data\benchmark\, saved to Documents\OrchSketch\Projects\Benchmark\, report benchmark_report.txt.
A chord expected as "unrecognized" must come out unrecognized and is then typed in by hand, as you would
(its "correct_to" symbol), before Confirm all.

It also checks SPEC §7's automatic pass/fail rules and writes testset_report.txt:
  * every chord's expected label is the best guess or among the alternatives,
  * no note outside its instrument's playable range,
  * no checker errors (and no generator_must_pass warnings) in generated output,
  * every alternative built, and the saved project reopens with exactly the same notes.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DATA = ROOT / "tests" / "data"
TESTSET = Path.home() / "Documents" / "OrchSketch" / "Projects" / "TestSet"
REPORT = ROOT / "testset_report.txt"
BENCHMARK_DATA = DATA / "benchmark"
BENCHMARK = Path.home() / "Documents" / "OrchSketch" / "Projects" / "Benchmark"
BENCHMARK_REPORT = ROOT / "benchmark_report.txt"
_APP = None  # the off-screen QApplication


def runs(data: Path = DATA) -> list[tuple[Path, bool]]:
    out = []
    for exp in sorted(data.glob("*.expected.json")):
        out.append((exp, False))
        if json.loads(exp.read_text(encoding="utf-8")).get("melody_file"):
            out.append((exp, True))
    return out


def project_stem(exp_path: Path, with_files: bool) -> str:
    return exp_path.name.split(".")[0] + ("_melody_bass" if with_files else "")


def run_one(exp_path: Path, with_files: bool, folder: Path) -> tuple[bool, list[str]]:
    data = exp_path.parent
    from PySide6.QtCore import QSettings

    from orchsketch import project as pj
    from orchsketch.generator import Orchestration, _must_fix
    from orchsketch.instruments import instruments
    from orchsketch.rules import ERROR, rules
    from orchsketch.theory import note_name
    from orchsketch.ui.main_window import MainWindow

    exp = json.loads(exp_path.read_text(encoding="utf-8"))
    stem = project_stem(exp_path, with_files)
    lines = [f"Test {str(exp['test']):>2}{' + melody and bass files' if with_files else ''}  ({exp['file']}, "
             f"{exp['key']['tonic']} {exp['key']['mode']}, {exp['bars']} bars)"]
    ok = True
    notes: list = []
    w = MainWindow()
    w.run_async = False
    w.notify = lambda title, text: notes.append(f"{title}: {text}")
    w.open_folder = lambda path: None
    w.show_menu = lambda menu: None
    w.ask_save = lambda: "discard"
    w.ask_save_path = lambda default: folder / f"{stem}.osk"
    w.settings = QSettings(str(folder / "_testset_settings.ini"), QSettings.IniFormat)
    w.projects_root = folder
    try:
        w.set_key(exp["key"]["tonic"], exp["key"]["mode"])
        assert w.load(data / exp["file"]), "the chord file was rejected"
        key = w.key()
        # labels: best guess, or the expected label among the alternatives (SPEC §7)
        res = w.session.chord_results
        bad = []
        best = 0
        typed = []
        for i, (r, e) in enumerate(zip(res, exp["chords"])):
            got = r.label.symbol(key) if r.label else "unrecognized"
            if got == e["label"]:
                best += 1
            elif e["label"] not in [a.symbol(key) for a in r.alternatives]:
                bad.append(f"{e['label']} read as {got}")
            if e.get("correct_to"):  # outside the v1 chord list: set by hand, as you would
                typed.append((i, e["correct_to"]))
        if len(res) != len(exp["chords"]):
            bad.append(f"{len(res)} chords found, {len(exp['chords'])} expected")
        ok &= not bad
        lines.append(f"  Labels: {best}/{len(exp['chords'])} best guess" + (f"  FAIL: {'; '.join(bad)}" if bad else
                                                                             "  (all correct)"))
        for i, text in typed:
            err = w.type_chord(i, text)
            assert err is None, f"chord {i + 1}: {err}"
        if typed:
            lines.append("  Set by hand: " + ", ".join(f"chord {i + 1} = {t}" for i, t in typed))
        w.confirm_all()
        if with_files:
            assert w.load_part_file("melody", data / exp["melody_file"])
            assert w.load_part_file("bass", data / exp["bass_file"])
        w.generate()
        insts, rl = instruments(), rules()
        for i, alt in enumerate("ABC"):
            o = w.alts[i]
            if not isinstance(o, Orchestration):
                ok = False
                lines.append(f"  {alt}: FAIL - not built: {o}")
                continue
            # generated output must be clean; problems only between your own inputs are shown (SPEC §7)
            must = _must_fix(o.report, rl, set(o.meta.get("fixed", set())))
            errors = [x for x in o.report.issues if x.severity == ERROR]
            out_of_range = []
            for ln in o.lines:
                inst = insts[ln.instrument]
                for n in o.part(ln.id).notes:
                    if not inst.playable[0] <= n.pitch <= inst.playable[1]:
                        out_of_range.append(f"{ln.label} {note_name(n.pitch, 'ableton', key)}")
            good = not must and not out_of_range
            ok &= good
            n_notes = sum(len(p.notes) for p in o.parts)
            lines.append(f"  {alt}: {'pass' if good else 'FAIL'} - {len(o.sounding_lines)} parts, {n_notes} notes, "
                         f"{len(must)} generator errors, {len(errors) - len([x for x in must if x.severity == ERROR])} from your "
                         f"own files, {len(o.report.warnings)} warnings"
                         + (f", outside playable: {', '.join(out_of_range[:5])}" if out_of_range else ""))
            lines.append(f"     {o.reason}")
            for x in must:
                lines.append(f"     ! {x.message}")
        path = w.save_project()
        reopened = pj.load(path)
        same = all((not isinstance(a, Orchestration) and a == b) or
                   (isinstance(a, Orchestration) and [p.notes for p in a.parts] == [p.notes for p in b.parts])
                   for a, b in zip(w.alts, reopened.alts))
        ok &= same
        lines.append(f"  Project: {path.name} ({path.stat().st_size // 1024} KB), "
                     f"{'reopens with the same notes' if same else 'FAIL - reopened notes differ'}")
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        ok = False
        lines.append(f"  FAIL - {exc!r}")
    for n in notes:
        lines.append(f"  (message: {n})")
    w.close()
    return ok, lines


def main(only: list[str] | None = None, folder: Path = TESTSET, report: Path | None = REPORT,
         data: Path = DATA) -> bool:
    from PySide6.QtWidgets import QApplication

    from orchsketch import __version__
    global _APP
    _APP = QApplication.instance() or QApplication([])
    folder.mkdir(parents=True, exist_ok=True)
    title = "second benchmark, your progressions" if data == BENCHMARK_DATA else "full test-set pass"
    out = [f"OrchSketch v{__version__} - {title} (SPEC §7-8)   {datetime.now():%Y-%m-%d %H:%M}",
           "Default preset (Full epic), safe mode, seed 1. Projects: " + str(folder), ""]
    total = passed = 0
    for exp, files in runs(data):
        if only and project_stem(exp, files) not in only:
            continue
        ok, lines = run_one(exp, files, folder)
        total += 1
        passed += ok
        out += lines + [""]
        print(lines[0], "-", "pass" if ok else "FAIL", flush=True)
    out.append(f"AUTOMATIC CHECKS: {passed}/{total} runs pass" + ("  -> OK" if passed == total else "  -> FAIL"))
    out.append("Next: the ear test. Open each project in the app and score A, B and C from 1 to 5.")
    if report is not None:
        report.write_text("\n".join(out) + "\n", encoding="utf-8")
    return passed == total


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--benchmark" in args:
        args.remove("--benchmark")
        ok = main(args or None, folder=BENCHMARK, report=BENCHMARK_REPORT, data=BENCHMARK_DATA)
    else:
        ok = main(args or None)
    sys.exit(0 if ok else 1)
