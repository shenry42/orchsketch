# OrchSketch — Status

> Read this first in every build chat, together with SPEC.md.
> The chat that finishes a milestone updates this file before it ends.

## Current state
- **Version:** v0.1
- **Last milestone completed:** 1 — Read and label
- **Next milestone:** 2 — Data and checker (SPEC.md §10)
- **Repo:** https://github.com/shenry42/orchsketch
- **Last updated:** 2026-11-11

## Milestones
- [x] 1 — v0.1 Read and label (+ packaging spike, audio test with Ableton open)
- [ ] 2 — v0.2 Data and checker (range + low-interval tables cross-checked)
- [ ] 3 — v0.3 First orchestration (safe mode, grid, playback, per-part export)
- [ ] 4 — v0.4 Control (A/B/C alternatives, lock, swap, undo, global sliders, presets)
- [ ] 5 — v0.5 Motion (patterns, bass, melody, moderate mode, per-section sliders)
- [ ] 6 — v1.0 Finish (projects, full export, .exe, full test-set pass, Ableton check)

## Test results (latest run)
- Automated tests: 105 passed / 0 failed (Windows, Python 3.12.10, `scripts\run_tests.bat`)
- Chord labels on 12-file test set: 12/12 correct, every chord as the best guess (not just among alternatives).
  Also stable under 60 random re-voicings per chord (spread, doubled, bass in octaves 1–3).
- Checker errors in generated output: — (no generator yet)
- Ear-test ratings: see tests/ratings.csv (avg score: —) (no orchestrations yet)
- Milestone 1 manual checks (Sam, 2026-11-11):
  - Packaged `.exe` played FluidSynth through WASAPI shared mode **while Ableton was playing on ASIO** (Focusrite): pass.
  - Ableton round trip (own clip → OrchSketch → export → drag into Arrangement): starts on the bar line, same length, same notes: pass.
  - App: load, labels, correction, confirm all: pass (after the click fix below).

## Known issues
- Chords over a non-chord bass show the Roman numeral as numeral + "/bass" (e.g. *Bb/C · VII/C*). Provisional notation; revisit if it reads badly.
- Diminished 7ths are named from the bass note (symmetrical chord): B–D–F–G# with B lowest reads *Bdim7 · ii°7*, not *vii°65*. The alternatives and typed correction cover it.
- Corrections only last while the app is open. Saving them is part of projects (Milestone 6).
- Melody and bass files: the reader exists and is tested, but there are no UI slots yet. They are first used in Milestone 5.
- Sam's real Ableton export isn't in the automated tests yet (the round trip was checked by hand). Add one Ableton-exported `.mid` to `tests/data/ableton/` when convenient.
- `Documents\OrchSketch` is both the Git repo and where the app writes `Exports\`, `Projects\` and `logs\` (git-ignored). Consider moving the repo to its own folder before v1.0.

## Decisions made during the build
<!-- Anything decided in a build chat that SPEC.md doesn't cover. Copy major ones into SPEC.md. -->
- **How builds happen (resolves SPEC §12 ".exe" item):** Claude edits files in `Documents\OrchSketch` through the linked folder. Claude's shell there is a Linux sandbox with no internet, and GitHub isn't linked to Claude. So every Windows step is a one-click script Sam runs: `setup.bat`, `run_tests.bat`, `run_app.bat`, `build_spike.bat`, `release.bat` (the last pushes with Sam's own Git login). Claude reads the logs these scripts write.
- **Minor key** = one setting that accepts both natural and harmonic minor chords (v and V, VII and vii°).
- **Test 8 and test 11 progressions** were written by Claude (see `tests/make_test_set.py`); Sam agreed to check them.
- **Grid snapping:** a note start more than 1/32 away from an 8th position is **rejected** with a message, not moved. Note ends snap to the nearest 8th (halves round up), so early releases never leave gaps.
- **Plain re-export** = the grid-snapped input notes as a type-0 MIDI file, 480 PPQ, 4/4, the tempo set in the app, starting at bar 1.
- **Labelling score:** template match minus missing/extra tones, plus bass role (root > 3rd > 5th > 7th > added tones), key fit and a small simplicity prior. Within a segment every pitch sounds for its full length, so SPEC's "duration weighting" has no effect in v1. The 5th may be omitted only in chords that have a 3rd and aren't 6/m6. A pedal favours "upper chord over the pedal".
- **Roman numeral conventions:** an added 6th is written *add6* (IIIadd6) so it isn't read as an inversion figure. Power and sus chords take the case of the diatonic triad on their root (*i5*, *VI5*, *IVsus2*). Inversions use 6/64 and 65/43/42.
- **FluidSynth opens its audio driver only, never a MIDI input driver**, so it can't take MIDI ports away from Ableton. WASAPI shared mode, default Windows output.
- **Versions:** FluidSynth 2.6.2 (official Windows x64 build), GeneralUser GS from its GitHub repo, PySide6 6.12, mido 1.3.3. The exact set is in `requirements.lock.txt`.
- **App data folder:** errors are logged to `Documents\OrchSketch\logs\error_log.txt`.

## Notes for the next chat
- Start Milestone 2 with `src/orchsketch/` data files: `instruments/*.json` (SPEC §4 record fields) and `rules` (low-interval limits). The checker should work on plain note lists so it can be tested without the UI.
- Range cross-check: Claude has no copy of Adler. Plan: compare each SPEC §4 value against published orchestration range references found on the web, list every difference with its source, and have Sam approve changes before they go in. Log approved changes in SPEC.md §4.
- Windows workflow: edit in the cloud workspace, pack a uniquely named `.tgz` into `_sync\`, unpack it in the linked folder, and copy over the files (deletes aren't allowed there, so `tar` can't overwrite; `cp` can). Ask Sam to run `scripts\run_tests.bat` and read `test_results.txt`.
- UI tests must never open a real popup or dialog (they block offscreen). Route them through replaceable methods like `MainWindow.show_menu`.
