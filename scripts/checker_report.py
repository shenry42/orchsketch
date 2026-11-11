"""Milestone 2 check for Sam: runs the rule checker on the hand-made examples and lists the
instrument ranges. Writes checker_report.txt in the repo folder (run scripts\\checker_report.bat)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import checker_examples as ex  # noqa: E402
from orchsketch import __version__  # noqa: E402
from orchsketch.checker import check  # noqa: E402
from orchsketch.instruments import instruments  # noqa: E402
from orchsketch.rules import rules  # noqa: E402
from orchsketch.theory import note_name  # noqa: E402


def main() -> int:
    out = [f"OrchSketch v{__version__} - rule checker report", "Note names are scientific (middle C = C4), as in SPEC.md. Ableton names are one octave lower.", ""]
    failures = 0
    out.append("== Hand-made examples (each should trigger exactly the listed checks)")
    for cid, desc, build, expected in ex.CASES:
        parts, chords, key = build()
        report = check(parts, chords, key, name_style="scientific")
        found = {i.check for i in report.issues}
        ok = found == expected
        failures += not ok
        out.append(f"[{'PASS' if ok else 'FAIL'}] {cid}: {desc}")
        out.append(f"       expected: {', '.join(sorted(expected)) or 'no problems'}")
        out.extend("       " + line for line in report.text().splitlines())
    out.append("")
    out.append("== Clean orchestrations (should have no problems)")
    for build in (ex.clean_epic_staple, ex.clean_harmonic_minor):
        parts, chords, key = build()
        report = check(parts, chords, key, name_style="scientific")
        failures += bool(report.issues)
        out.append(f"[{'PASS' if not report.issues else 'FAIL'}] {build.__doc__.splitlines()[0]}")
        out.extend("       " + line for line in report.text().splitlines())
    out.append("")
    out.append("== Instrument ranges (sounding)")
    out.append(f"{'Instrument':16} {'Playable':12} {'Comfortable':12} {'Ableton: playable':18} comfortable")
    for inst in instruments().values():
        out.append(f"{inst.name:16} {inst.range_text('playable', 'scientific'):12} "
                   f"{inst.range_text('comfortable', 'scientific'):12} "
                   f"{inst.range_text('playable', 'ableton'):18} {inst.range_text('comfortable', 'ableton')}")
    out.append("")
    out.append("== Low-interval limits (lowest allowed lower note)")
    r = rules()
    for semis, pitch in sorted(r.low_interval_limits.items()):
        out.append(f"{r.interval_names.get(semis, semis):12} {note_name(pitch, 'scientific')}")
    out.append("")
    out.append("RESULT: " + ("ALL PASS" if not failures else f"{failures} FAILED"))
    (ROOT / "checker_report.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("RESULT: " + ("ALL PASS" if not failures else f"{failures} FAILED"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
