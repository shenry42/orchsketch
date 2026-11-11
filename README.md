# OrchSketch

A Windows desktop app for sketching orchestrations from a block-chord MIDI clip. It labels the harmony,
then (from Milestone 3) generates rule-checked string, brass, woodwind and choir parts to audition and
drag into Ableton. Personal use. Full design: [SPEC.md](SPEC.md). Current state: [STATUS.md](STATUS.md).
History: [CHANGELOG.md](CHANGELOG.md).

## Using it (Windows)
All scripts are in `scripts\` - double-click them.

| Script | What it does |
| --- | --- |
| `setup.bat` | One-time: installs Python 3.12, the packages, FluidSynth and the GeneralUser GS SoundFont, links Git. Safe to re-run. |
| `run_app.bat` | Starts OrchSketch. |
| `run_tests.bat` | Runs the automated tests; full output in `test_results.txt`. |
| `build_spike.bat` | Milestone 1 throwaway: builds the audio test `.exe`. |
| `release.bat` | Tests, commits, tags the version, pushes, and writes `releases\orchsketch-vX.Y-src.zip`. |
| `checker_report.bat` | Runs the rule checker on the hand-made examples and opens `checker_report.txt`. |
| `check_prereqs.bat` | Lists what's installed (writes `prereqs.txt`). |

## Layout
```
src/orchsketch/
  midi_io.py        read/write MIDI (mido); everything at 480 PPQ, bar 1 = tick 0
  theory.py         keys, spelling, note names (Ableton C3 = scientific C4 = MIDI 60)
  analysis/         segmentation, chord labels + alternatives, Roman numerals, corrections
  instruments.py    instrument records (ranges, roles, GM program, timbre notes) from data/instruments/*.json
  rules.py          low-interval limits, spacing/leap limits, check severities from data/rules.json
  checker.py        rule checker on plain note lists (SPEC §7), no UI
  data/             the JSON data files (edit these to change a range or a limit)
  playback/         FluidSynth helpers (audition arrives in Milestone 3)
  ui/               PySide6 window (the only package that imports Qt)
tests/              pytest suite; tests/data holds the 12-progression test set
scripts/            Windows .bat helpers and the audio spike
```
`vendor\` (FluidSynth, SoundFont) and `.venv\` are created by `setup.bat` and aren't in Git.

## Third-party
- FluidSynth (LGPL-2.1) is downloaded by setup from the official GitHub releases.
- GeneralUser GS SoundFont by S. Christian Collins; licence to be confirmed in Milestone 3 (see SPEC §12).
